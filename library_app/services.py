from __future__ import annotations
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
import re, sqlite3
from .security import hash_password, verify_password

class LibraryError(Exception): pass

class LibraryService:
    def __init__(self, db): self.db = db

    def bootstrap_users(self, admin_password: str, librarian_passwords: list[str]):
        if len(librarian_passwords) != 4: raise ValueError('Exactly four initial librarian passwords are required.')
        with self.db.connect() as c:
            if c.execute('SELECT COUNT(*) FROM users').fetchone()[0]: return False
            for username, role, password in [('admin','ADMIN',admin_password)] + [(f'librarian{i}','LIBRARIAN',p) for i,p in enumerate(librarian_passwords,1)]:
                digest, salt = hash_password(password)
                c.execute('INSERT INTO users(username,password_hash,password_salt,role) VALUES(?,?,?,?)',(username,digest,salt,role))
        return True

    def authenticate(self, username, password):
        with self.db.connect() as c:
            row=c.execute('SELECT * FROM users WHERE username=? AND active=1',(username.strip(),)).fetchone()
        if not row or not verify_password(password,row['password_hash'],row['password_salt']): return None
        return dict(row)

    @staticmethod
    def require_admin(user):
        if not user or user.get('role') != 'ADMIN': raise PermissionError('Administrator permission is required.')

    def change_password(self, user, target_username, new_password):
        if user.get('role') != 'ADMIN' and user.get('username') != target_username: raise PermissionError('You may change only your own password.')
        digest,salt=hash_password(new_password)
        with self.db.connect() as c:
            cur=c.execute('UPDATE users SET password_hash=?,password_salt=? WHERE username=? AND active=1',(digest,salt,target_username))
            if cur.rowcount != 1: raise LibraryError('User was not found or is inactive.')

    def add_member(self, user, data):
        if not user or user.get('role') not in ('ADMIN','LIBRARIAN'): raise PermissionError('Login required.')
        name=(data.get('name') or '').strip(); member_id=(data.get('member_id') or '').strip()
        if not name or not member_id: raise ValueError('Member ID and member name are mandatory.')
        mobile=(data.get('mobile') or '').strip()
        if mobile and not re.fullmatch(r'[+0-9() -]{7,20}',mobile): raise ValueError('Mobile number contains invalid characters or length.')
        with self.db.connect() as c:
            c.execute('INSERT INTO members(member_id,sno,name,father_name,address,registration_no,mobile,registration_date,status,remarks) VALUES(?,?,?,?,?,?,?,?,?,?)',
                (member_id,data.get('sno'),name,data.get('father_name'),data.get('address'),data.get('registration_no') or None,mobile,data.get('registration_date') or date.today().isoformat(),data.get('status') or 'ACTIVE',data.get('remarks')))
            return c.execute('SELECT last_insert_rowid()').fetchone()[0]

    def add_book(self, user, data, copies):
        if not user or user.get('role') not in ('ADMIN','LIBRARIAN'): raise PermissionError('Login required.')
        title=(data.get('title') or '').strip()
        if not title: raise ValueError('Book title is mandatory.')
        if not copies: raise ValueError('At least one physical copy is required.')
        with self.db.connect() as c:
            cur=c.execute('INSERT INTO books(title,author,publisher,edition,isbn,language,page_count,category,publication_year,cover_path,acquisition_date,source,cost,remarks) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
              (title,data.get('author'),data.get('publisher'),data.get('edition'),data.get('isbn'),data.get('language'),data.get('page_count'),data.get('category'),data.get('publication_year'),data.get('cover_path'),data.get('acquisition_date'),data.get('source'),data.get('cost'),data.get('remarks')))
            book_id=cur.lastrowid
            for copy in copies:
                acc=(copy.get('accession_no') or '').strip()
                if not acc: raise ValueError('Every copy must have an accession number.')
                loc_id=None
                rack=(copy.get('rack') or '').strip()
                if rack:
                    c.execute('INSERT OR IGNORE INTO locations(rack,shelf,compartment) VALUES(?,?,?)',(rack,copy.get('shelf') or '',copy.get('compartment') or ''))
                    loc_id=c.execute('SELECT id FROM locations WHERE rack=? AND shelf=? AND compartment=?',(rack,copy.get('shelf') or '',copy.get('compartment') or '')).fetchone()[0]
                c.execute('INSERT INTO book_copies(accession_no,book_id,location_id,remarks) VALUES(?,?,?,?)',(acc,book_id,loc_id,copy.get('remarks')))
            self.audit(c,user,'BOOK_CREATED','book',book_id,f'{title}; copies={len(copies)}')
            return book_id

    def search_books(self, query='', limit=100):
        with self.db.connect() as c:
            rows=c.execute('''SELECT b.*, COUNT(cp.id) total_copies,
                SUM(CASE WHEN cp.status='AVAILABLE' THEN 1 ELSE 0 END) available_copies,
                GROUP_CONCAT(DISTINCT CASE WHEN cp.status='AVAILABLE' THEN COALESCE(l.rack,'Unassigned')||' / '||COALESCE(l.shelf,'')||' / '||COALESCE(l.compartment,'') END) locations
                FROM books b LEFT JOIN book_copies cp ON cp.book_id=b.id LEFT JOIN locations l ON l.id=cp.location_id
                WHERE b.archived=0 GROUP BY b.id''').fetchall()
        q=query.casefold().strip()
        if not q: return [dict(r) for r in rows[:limit]]
        ranked=[]
        for r in rows:
            fields=[r['title'],r['author'],r['isbn'],r['language'],r['category']]
            text=' '.join(str(x or '') for x in fields).casefold()
            score=max([SequenceMatcher(None,q,str(x or '').casefold()).ratio() for x in fields]+([1.0] if q in text else [0.0]))
            if score >= 0.35: ranked.append((score,dict(r)))
        return [x[1] for x in sorted(ranked,key=lambda x:x[0],reverse=True)[:limit]]

    def issue_book(self,user,accession_no,member_id,loan_days=15,issue_date=None):
        if not user or user.get('role') not in ('ADMIN','LIBRARIAN'): raise PermissionError('Login required.')
        if loan_days not in (7,15,21,28): raise ValueError('Loan period must be 7, 15, 21, or 28 days.')
        issue_date=date.fromisoformat(issue_date) if issue_date else date.today()
        with self.db.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            member=c.execute('SELECT * FROM members WHERE member_id=?',(member_id,)).fetchone()
            if not member: raise LibraryError('Member not found.')
            if member['status']!='ACTIVE': raise LibraryError('Cannot issue to an inactive or suspended member.')
            copy=c.execute('SELECT * FROM book_copies WHERE accession_no=?',(accession_no,)).fetchone()
            if not copy: raise LibraryError('Accession number not found.')
            if copy['status']!='AVAILABLE': raise LibraryError('This copy is not available.')
            active_count=c.execute("SELECT COUNT(*) FROM loans WHERE member_id=? AND status='ACTIVE'",(member['id'],)).fetchone()[0]
            if active_count >= 2: raise LibraryError('A member may hold a maximum of 2 books at a time. Return a book before issuing another.')
            due=issue_date+timedelta(days=loan_days)
            c.execute('INSERT INTO loans(copy_id,member_id,issued_by,issue_date,due_date,loan_days,status) VALUES(?,?,?,?,?,?,\'ACTIVE\')',(copy['id'],member['id'],user['id'],issue_date.isoformat(),due.isoformat(),loan_days))
            c.execute("UPDATE book_copies SET status='ISSUED' WHERE id=?",(copy['id'],))
            self.audit(c,user,'BOOK_ISSUED','loan',c.execute('SELECT last_insert_rowid()').fetchone()[0],f'{accession_no} to {member_id}; due {due}')
            return due.isoformat()

    def return_book(self,user,accession_no,return_date=None):
        if not user or user.get('role') not in ('ADMIN','LIBRARIAN'): raise PermissionError('Login required.')
        ret=date.fromisoformat(return_date) if return_date else date.today()
        with self.db.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            loan=c.execute('''SELECT lo.*,cp.accession_no,me.member_id FROM loans lo JOIN book_copies cp ON cp.id=lo.copy_id JOIN members me ON me.id=lo.member_id WHERE cp.accession_no=? AND lo.status='ACTIVE' ''',(accession_no,)).fetchone()
            if not loan: raise LibraryError('No active loan exists for this copy.')
            rule=c.execute('SELECT * FROM penalty_rules WHERE effective_from<=? ORDER BY effective_from DESC,id DESC LIMIT 1',(ret.isoformat(),)).fetchone()
            overdue=max(0,(ret-date.fromisoformat(loan['due_date'])).days)
            amount=0.0
            if rule:
                billable=max(0,overdue-rule['grace_days'])
                if rule['count_partial_day'] and ret>date.fromisoformat(loan['due_date']): billable=max(1,billable)
                amount=billable*rule['rate_per_day']
                if rule['max_penalty'] is not None: amount=min(amount,rule['max_penalty'])
            c.execute("UPDATE loans SET status='RETURNED',return_date=?,returned_to=? WHERE id=?",(ret.isoformat(),user['id'],loan['id']))
            c.execute("UPDATE book_copies SET status='AVAILABLE' WHERE id=?",(loan['copy_id'],))
            if overdue:
                c.execute('INSERT INTO penalty_assessments(loan_id,overdue_days,amount) VALUES(?,?,?)',(loan['id'],overdue,amount))
            reservation=c.execute("SELECT r.id,r.member_id,m.member_id member_code,m.name member_name,b.title book_title FROM reservations r JOIN members m ON m.id=r.member_id JOIN books b ON b.id=r.book_id WHERE r.book_id=(SELECT book_id FROM book_copies WHERE id=?) AND r.status='WAITING' ORDER BY r.requested_at,r.id LIMIT 1",(loan['copy_id'],)).fetchone()
            if reservation:
                c.execute("UPDATE reservations SET status='NOTIFIED',notified_at=CURRENT_TIMESTAMP WHERE id=?",(reservation['id'],))
            self.audit(c,user,'BOOK_RETURNED','loan',loan['id'],f'{accession_no}; overdue={overdue}; penalty={amount:.2f}')
            return {'overdue_days':overdue,'penalty':round(amount,2),'notified_member_id':reservation['member_code'] if reservation else None,'notified_member_name':reservation['member_name'] if reservation else None,'notified_book_title':reservation['book_title'] if reservation else None}

    def add_reservation(self,user,book_id,member_id):
        if not user or user.get('role') not in ('ADMIN','LIBRARIAN'): raise PermissionError('Login required.')
        with self.db.connect() as c:
            member=c.execute('SELECT id,status FROM members WHERE member_id=?',(member_id,)).fetchone()
            if not member or member['status']!='ACTIVE': raise LibraryError('Active member not found.')
            available=c.execute("SELECT COUNT(*) FROM book_copies WHERE book_id=? AND status='AVAILABLE'",(book_id,)).fetchone()[0]
            if available: raise LibraryError('Copies are currently available; reservation is not required.')
            existing=c.execute("SELECT id FROM reservations WHERE book_id=? AND member_id=? AND status IN ('WAITING','NOTIFIED')",(book_id,member['id'])).fetchone()
            if existing: raise LibraryError('This member is already on the waiting list for this title.')
            c.execute("INSERT INTO reservations(book_id,member_id) VALUES(?,?)",(book_id,member['id']))
            self.audit(c,user,'WAITLIST_ADDED','reservation',c.execute('SELECT last_insert_rowid()').fetchone()[0],f'book={book_id}; member={member_id}')

    def delete_member(self, user, member_id):
        """Admin-only delete; preserve referenced member history by deactivating instead."""
        self.require_admin(user)
        with self.db.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            member=c.execute('SELECT * FROM members WHERE member_id=?',(member_id,)).fetchone()
            if not member: raise LibraryError('Member not found.')
            has_history=c.execute('SELECT 1 FROM loans WHERE member_id=? LIMIT 1',(member['id'],)).fetchone() or c.execute('SELECT 1 FROM penalty_payments WHERE member_id=? LIMIT 1',(member['id'],)).fetchone() or c.execute('SELECT 1 FROM reservations WHERE member_id=? LIMIT 1',(member['id'],)).fetchone()
            if has_history:
                c.execute("UPDATE members SET status='INACTIVE' WHERE id=?",(member['id'],))
                action='MEMBER_ARCHIVED'
                result='archived (historical records preserved)'
            else:
                c.execute('DELETE FROM members WHERE id=?',(member['id'],))
                action='MEMBER_DELETED'; result='deleted'
            self.audit(c,user,action,'member',member['id'],member['member_id'])
            return result

    def delete_book(self, user, book_id):
        """Admin-only delete; archive any title whose copies have circulation history."""
        self.require_admin(user)
        with self.db.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            book=c.execute('SELECT * FROM books WHERE id=? AND archived=0',(book_id,)).fetchone()
            if not book: raise LibraryError('Book not found or already archived.')
            has_history=c.execute('SELECT 1 FROM loans lo JOIN book_copies cp ON cp.id=lo.copy_id WHERE cp.book_id=? LIMIT 1',(book_id,)).fetchone()
            active=c.execute("SELECT 1 FROM book_copies WHERE book_id=? AND status='ISSUED' LIMIT 1",(book_id,)).fetchone()
            if active: raise LibraryError('Cannot delete a book while any copy is currently issued. Process all returns first.')
            if has_history:
                c.execute('UPDATE books SET archived=1 WHERE id=?',(book_id,))
                c.execute("UPDATE book_copies SET status='WITHDRAWN' WHERE book_id=? AND status='AVAILABLE'",(book_id,))
                c.execute("UPDATE reservations SET status='CANCELLED' WHERE book_id=? AND status IN ('WAITING','NOTIFIED')",(book_id,))
                action='BOOK_ARCHIVED'; result='archived (historical records preserved)'
            else:
                c.execute("DELETE FROM reservations WHERE book_id=?",(book_id,))
                c.execute('DELETE FROM book_copies WHERE book_id=?',(book_id,))
                c.execute('DELETE FROM books WHERE id=?',(book_id,))
                action='BOOK_DELETED'; result='deleted'
            self.audit(c,user,action,'book',book_id,book['title'])
            return result

    def configure_penalty(self,user,rate,effective_from=None,grace_days=0,max_penalty=None,count_partial_day=False,notes=''):
        self.require_admin(user)
        if rate<0 or grace_days<0 or (max_penalty is not None and max_penalty<0): raise ValueError('Penalty settings cannot be negative.')
        eff=effective_from or date.today().isoformat()
        with self.db.connect() as c:
            c.execute('INSERT INTO penalty_rules(rate_per_day,effective_from,grace_days,max_penalty,count_partial_day,notes,created_by) VALUES(?,?,?,?,?,?,?)',(rate,eff,grace_days,max_penalty,int(count_partial_day),notes,user['id']))
            self.audit(c,user,'PENALTY_RULE_CHANGED','penalty_rule',c.execute('SELECT last_insert_rowid()').fetchone()[0],f'rate={rate}; effective={eff}')

    def record_payment(self,user,member_id,amount,payment_date=None,receipt_no=None,notes=''):
        if not user or user.get('role') not in ('ADMIN','LIBRARIAN'): raise PermissionError('Login required.')
        if amount<=0: raise ValueError('Payment must be greater than zero.')
        with self.db.connect() as c:
            m=c.execute('SELECT id FROM members WHERE member_id=?',(member_id,)).fetchone()
            if not m: raise LibraryError('Member not found.')
            c.execute('INSERT INTO penalty_payments(member_id,amount,payment_date,received_by,receipt_no,notes) VALUES(?,?,?,?,?,?)',(m['id'],amount,payment_date or date.today().isoformat(),user['id'],receipt_no or None,notes))

    def reports(self):
        with self.db.connect() as c:
            return {
              'active_loans':[dict(r) for r in c.execute("SELECT lo.id,cp.accession_no,b.title,m.member_id,m.name,lo.issue_date,lo.due_date,u.username librarian FROM loans lo JOIN book_copies cp ON cp.id=lo.copy_id JOIN books b ON b.id=cp.book_id JOIN members m ON m.id=lo.member_id JOIN users u ON u.id=lo.issued_by WHERE lo.status='ACTIVE' ORDER BY lo.due_date")],
              'overdue':[dict(r) for r in c.execute("SELECT cp.accession_no,b.title,m.member_id,m.name,lo.due_date,CAST(julianday('now')-julianday(lo.due_date) AS INTEGER) overdue_days FROM loans lo JOIN book_copies cp ON cp.id=lo.copy_id JOIN books b ON b.id=cp.book_id JOIN members m ON m.id=lo.member_id WHERE lo.status='ACTIVE' AND lo.due_date<date('now') ORDER BY lo.due_date")],
              'waiting':[dict(r) for r in c.execute("SELECT b.title,m.member_id,m.name,r.requested_at,r.status FROM reservations r JOIN books b ON b.id=r.book_id JOIN members m ON m.id=r.member_id WHERE r.status IN ('WAITING','NOTIFIED') ORDER BY r.requested_at")],
              'inventory':[dict(r) for r in c.execute("SELECT b.id,b.title,b.author,b.category,COUNT(cp.id) total_copies,SUM(CASE WHEN cp.status='AVAILABLE' THEN 1 ELSE 0 END) available_copies,SUM(CASE WHEN cp.status='ISSUED' THEN 1 ELSE 0 END) issued_copies FROM books b LEFT JOIN book_copies cp ON cp.book_id=b.id WHERE b.archived=0 GROUP BY b.id ORDER BY b.title")]
            }

    @staticmethod
    def audit(c,user,action,entity_type,entity_id,details=''):
        c.execute('INSERT INTO audit_log(user_id,action,entity_type,entity_id,details) VALUES(?,?,?,?,?)',(user['id'],action,entity_type,str(entity_id),details))
