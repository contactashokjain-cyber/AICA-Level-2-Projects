from __future__ import annotations
import os, sys, shutil, logging, tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from pathlib import Path
from datetime import date
from .db import Database
from .services import LibraryService, LibraryError
from .io_utils import import_rows, export_xlsx, export_pdf, export_template, BOOK_FIELDS, MEMBER_FIELDS

APP_DIR=Path(os.environ.get('LOCALAPPDATA',Path.home()))/'SocietyLibrary'
APP_DIR.mkdir(parents=True,exist_ok=True)
(APP_DIR/'covers').mkdir(exist_ok=True); (APP_DIR/'backups').mkdir(exist_ok=True); (APP_DIR/'logs').mkdir(exist_ok=True)
logging.basicConfig(filename=APP_DIR/'logs'/'library.log',level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')

class LibraryApp(tk.Tk):
    def __init__(self):
        super().__init__(); self.title('Society Library Management System'); self.geometry('1360x850'); self.minsize(1080,700)
        self._configure_style()
        self.db=Database(APP_DIR/'library.sqlite3'); self.svc=LibraryService(self.db); self.user=None
        self.protocol('WM_DELETE_WINDOW',self.close_app)
        self.show_login()

    def _configure_style(self):
        # Ocean-blue palette with pale blue surfaces for a brighter, calmer interface.
        self.palette = {'ocean':'#075985', 'blue':'#0284C7', 'teal':'#0F766E',
                        'light':'#EAF6FC', 'surface':'#F7FBFE', 'white':'#FFFFFF',
                        'ink':'#123047', 'muted':'#496579', 'line':'#B9DCEB',
                        'selected':'#C7EAF8'}
        self.configure(background=self.palette['light'])
        style=ttk.Style(self)
        try: style.theme_use('clam')
        except tk.TclError: pass
        p=self.palette
        style.configure('.', font=('Segoe UI', 12), background=p['light'], foreground=p['ink'])
        style.configure('TFrame', background=p['light'])
        style.configure('TLabel', font=('Segoe UI', 12), background=p['light'], foreground=p['ink'])
        style.configure('TButton', font=('Segoe UI', 12, 'bold'), padding=(12, 8),
                        background=p['blue'], foreground=p['white'], borderwidth=0)
        style.map('TButton', background=[('active',p['ocean']),('pressed',p['ocean'])],
                  foreground=[('disabled','#8CA6B5')])
        style.configure('TEntry', font=('Segoe UI', 12), padding=6, fieldbackground=p['white'])
        style.configure('TCombobox', font=('Segoe UI', 12), padding=6, fieldbackground=p['white'])
        style.configure('TLabelframe', background=p['light'], bordercolor=p['line'], relief='solid')
        style.configure('TLabelframe.Label', font=('Segoe UI', 13, 'bold'), background=p['light'], foreground=p['ocean'])
        style.configure('Treeview', font=('Segoe UI', 11), rowheight=32,
                        background=p['white'], fieldbackground=p['white'], foreground=p['ink'])
        style.configure('Treeview.Heading', font=('Segoe UI', 11, 'bold'), padding=8,
                        background=p['ocean'], foreground=p['white'])
        style.map('Treeview', background=[('selected',p['selected'])], foreground=[('selected',p['ink'])])
        style.configure('TNotebook', background=p['light'], borderwidth=0, tabmargins=(3,3,3,0))
        style.configure('TNotebook.Tab', font=('Segoe UI', 11, 'bold'), padding=(14, 10),
                        background='#D5EDF7', foreground=p['ocean'])
        style.map('TNotebook.Tab', background=[('selected',p['ocean']),('active',p['selected'])],
                  foreground=[('selected',p['white']),('active',p['ocean'])])
        style.configure('Vertical.TScrollbar', background='#B5DDEB', troughcolor=p['light'], arrowcolor=p['ocean'])

    def clear(self):
        for w in self.winfo_children(): w.destroy()

    def show_login(self):
        self.clear(); frame=ttk.Frame(self,padding=32); frame.pack(expand=True)
        ttk.Label(frame,text='Society Library',font=('Segoe UI',22,'bold')).grid(row=0,column=0,columnspan=2,pady=(0,18))
        count=self.db.connect().execute('SELECT COUNT(*) FROM users').fetchone()[0]
        if count==0:
            ttk.Label(frame,text='First-time setup: create the Admin and four Librarian accounts.').grid(row=1,column=0,columnspan=2,pady=6)
            fields=[('Admin password','admin_pw'),('Confirm admin password','admin_confirm')]+[(f'Librarian {i} password',f'lib{i}') for i in range(1,5)]
            entries={}
            for n,(label,key) in enumerate(fields,2):
                ttk.Label(frame,text=label).grid(row=n,column=0,sticky='w',padx=6,pady=5)
                e=ttk.Entry(frame,show='*',width=32); e.grid(row=n,column=1,pady=5); entries[key]=e
            ttk.Label(frame,text='Minimum 10 characters per password. Usernames: admin, librarian1–librarian4').grid(row=8,column=0,columnspan=2,pady=8)
            def setup():
                try:
                    a=entries['admin_pw'].get()
                    if a!=entries['admin_confirm'].get(): raise ValueError('Admin passwords do not match.')
                    self.svc.bootstrap_users(a,[entries[f'lib{i}'].get() for i in range(1,5)])
                    messagebox.showinfo('Setup complete','Accounts created. Sign in with username admin.'); self.show_login()
                except Exception as ex: messagebox.showerror('Setup error',str(ex))
            ttk.Button(frame,text='Create local accounts',command=setup).grid(row=9,column=0,columnspan=2,pady=12)
        else:
            ttk.Label(frame,text='Sign in to continue').grid(row=1,column=0,columnspan=2,pady=6)
            ttk.Label(frame,text='Username').grid(row=2,column=0,sticky='w',pady=6); u=ttk.Entry(frame,width=32); u.grid(row=2,column=1,pady=6)
            ttk.Label(frame,text='Password').grid(row=3,column=0,sticky='w',pady=6); p=ttk.Entry(frame,show='*',width=32); p.grid(row=3,column=1,pady=6)
            def login():
                user=self.svc.authenticate(u.get(),p.get())
                if not user: messagebox.showerror('Sign-in failed','Invalid credentials or inactive account.'); return
                self.user=user; self.show_main()
            ttk.Button(frame,text='Sign in',command=login).grid(row=4,column=0,columnspan=2,pady=12)
            p.bind('<Return>',lambda _e:login()); u.focus_set()

    def show_main(self):
        self.clear(); top=ttk.Frame(self,padding=8); top.pack(fill='x')
        ttk.Label(top,text='Society Library Management System',font=('Segoe UI',16,'bold')).pack(side='left')
        ttk.Label(top,text=f"Signed in: {self.user['username']} ({self.user['role']})").pack(side='right')
        ttk.Button(top,text='Log out',command=self.logout).pack(side='right',padx=10)
        self.nb=ttk.Notebook(self); self.nb.pack(fill='both',expand=True,padx=8,pady=8)
        self.dashboard_tab(); self.books_tab(); self.members_tab(); self.circulation_tab(); self.reports_tab()
        self.password_tab()
        if self.user['role']=='ADMIN': self.admin_tab()

    def logout(self): self.user=None; self.show_login()

    def dashboard_tab(self):
        f=ttk.Frame(self.nb,padding=18); self.nb.add(f,text='Dashboard')
        ttk.Label(f,text='Library overview',font=('Segoe UI',17,'bold')).pack(anchor='w',pady=(0,12))
        with self.db.connect() as c:
            stats=[('Book titles',c.execute('SELECT COUNT(*) FROM books WHERE archived=0').fetchone()[0]),
                   ('Physical copies',c.execute('SELECT COUNT(*) FROM book_copies').fetchone()[0]),
                   ('Available copies',c.execute("SELECT COUNT(*) FROM book_copies WHERE status='AVAILABLE'").fetchone()[0]),
                   ('Total members',c.execute('SELECT COUNT(*) FROM members').fetchone()[0]),
                   ('Active members',c.execute("SELECT COUNT(*) FROM members WHERE status='ACTIVE'").fetchone()[0]),
                   ('Active issues',c.execute("SELECT COUNT(*) FROM loans WHERE status='ACTIVE'").fetchone()[0]),
                   ('Overdue issues',c.execute("SELECT COUNT(*) FROM loans WHERE status='ACTIVE' AND due_date<date('now')").fetchone()[0]),
                   ('Waiting reservations',c.execute("SELECT COUNT(*) FROM reservations WHERE status IN ('WAITING','NOTIFIED')").fetchone()[0])]
        grid=ttk.Frame(f); grid.pack(fill='x',anchor='nw')
        for i,(label,value) in enumerate(stats):
            card=ttk.LabelFrame(grid,text=label,padding=18); card.grid(row=i//4,column=i%4,padx=8,pady=8,sticky='nsew')
            ttk.Label(card,text=str(value),font=('Segoe UI',24,'bold'),foreground=self.palette['blue']).pack()
            grid.columnconfigure(i%4,weight=1)
        ttk.Label(f,text='Data and photographs are stored on this computer. No internet connection is required.',foreground='#555').pack(anchor='w',pady=20)

    def _tree(self,parent,columns,height=14):
        frame=ttk.Frame(parent); frame.pack(fill='both',expand=True,pady=6)
        tree=ttk.Treeview(frame,columns=columns,show='headings',height=height)
        for col in columns: tree.heading(col,text=col.replace('_',' ').title()); tree.column(col,width=130,anchor='w')
        vs=ttk.Scrollbar(frame,orient='vertical',command=tree.yview); hs=ttk.Scrollbar(frame,orient='horizontal',command=tree.xview)
        tree.configure(yscrollcommand=vs.set,xscrollcommand=hs.set); tree.grid(row=0,column=0,sticky='nsew'); vs.grid(row=0,column=1,sticky='ns'); hs.grid(row=1,column=0,sticky='ew'); frame.rowconfigure(0,weight=1); frame.columnconfigure(0,weight=1)
        return tree

    def books_tab(self):
        f=ttk.Frame(self.nb,padding=10); self.nb.add(f,text='Books & Search')
        bar=ttk.Frame(f); bar.pack(fill='x'); ttk.Label(bar,text='Search books').pack(side='left')
        q=ttk.Entry(bar,width=40); q.pack(side='left',padx=6); ttk.Button(bar,text='Search',command=lambda:refresh()).pack(side='left')
        ttk.Button(bar,text='Add book',command=self.add_book_dialog).pack(side='right',padx=3)
        ttk.Button(bar,text='Import books',command=self.import_books).pack(side='right',padx=3)
        ttk.Button(bar,text='Export books',command=self.export_books).pack(side='right',padx=3)
        if self.user['role']=='ADMIN': ttk.Button(bar,text='Delete / Archive selected',command=lambda:self.delete_selected_book(tree)).pack(side='right',padx=3)
        cols=('id','title','author','isbn','language','category','total_copies','available_copies','locations')
        tree=self._tree(f,cols)
        def refresh():
            tree.delete(*tree.get_children())
            for r in self.svc.search_books(q.get()): tree.insert('', 'end',values=tuple(r.get(k,'') if r.get(k) is not None else '' for k in cols))
        q.bind('<Return>',lambda _e:refresh()); refresh()

    def add_book_dialog(self):
        win=tk.Toplevel(self); win.title('Add book and physical copies'); win.geometry('650x700'); win.transient(self); win.grab_set()
        canvas=tk.Canvas(win); sb=ttk.Scrollbar(win,orient='vertical',command=canvas.yview); inner=ttk.Frame(canvas,padding=14)
        inner.bind('<Configure>',lambda _e:canvas.configure(scrollregion=canvas.bbox('all'))); canvas.create_window((0,0),window=inner,anchor='nw'); canvas.configure(yscrollcommand=sb.set); canvas.pack(side='left',fill='both',expand=True); sb.pack(side='right',fill='y')
        fields=['title','author','publisher','edition','isbn','language','page_count','category','publication_year','cover_path','acquisition_date','source','cost','remarks','accession_no','rack','shelf','compartment']
        entries={}
        for i,key in enumerate(fields):
            ttk.Label(inner,text=key.replace('_',' ').title()).grid(row=i,column=0,sticky='w',pady=3)
            e=ttk.Entry(inner,width=48); e.grid(row=i,column=1,sticky='ew',pady=3); entries[key]=e
        entries['acquisition_date'].insert(0,date.today().isoformat())
        def choose_cover():
            p=filedialog.askopenfilename(parent=win,title='Choose book cover',filetypes=[('Images','*.png *.jpg *.jpeg *.gif *.bmp')])
            if p:
                dest=APP_DIR/'covers'/Path(p).name
                if Path(p).resolve()!=dest.resolve(): shutil.copy2(p,dest)
                entries['cover_path'].delete(0,'end'); entries['cover_path'].insert(0,str(dest))
        ttk.Button(inner,text='Choose cover image',command=choose_cover).grid(row=len(fields),column=1,sticky='w',pady=4)
        def save():
            d={k:e.get().strip() or None for k,e in entries.items()}
            for k in ('page_count','publication_year'):
                if d[k] is not None: d[k]=int(d[k])
            if d['cost'] is not None: d['cost']=float(d['cost'])
            copy={k:d.pop(k) for k in ('accession_no','rack','shelf','compartment')}
            try: self.svc.add_book(self.user,d,[copy]); messagebox.showinfo('Saved','Book and copy added.',parent=win); win.destroy(); self.show_main()
            except Exception as ex: messagebox.showerror('Cannot save',str(ex),parent=win)
        ttk.Button(inner,text='Save book',command=save).grid(row=len(fields)+1,column=1,sticky='e',pady=12)

    def members_tab(self):
        f=ttk.Frame(self.nb,padding=10); self.nb.add(f,text='Members')
        bar=ttk.Frame(f); bar.pack(fill='x'); ttk.Button(bar,text='Add member',command=self.add_member_dialog).pack(side='left'); ttk.Button(bar,text='Import members',command=self.import_members).pack(side='left',padx=6); ttk.Button(bar,text='Export members',command=self.export_members).pack(side='left')
        if self.user['role']=='ADMIN': ttk.Button(bar,text='Delete / Deactivate selected',command=lambda:self.delete_selected_member(tree)).pack(side='right')
        cols=('member_id','sno','name','father_name','mobile','registration_no','registration_date','status')
        tree=self._tree(f,cols)
        with self.db.connect() as c: rows=c.execute('SELECT member_id,sno,name,father_name,mobile,registration_no,registration_date,status FROM members ORDER BY name').fetchall()
        for r in rows: tree.insert('','end',values=tuple(r[k] or '' for k in cols))

    def add_member_dialog(self):
        win=tk.Toplevel(self); win.title('Register member'); win.geometry('520x500'); win.transient(self); win.grab_set()
        fields=['member_id','sno','name','father_name','address','registration_no','mobile','registration_date','status','remarks']; entries={}
        for i,k in enumerate(fields):
            ttk.Label(win,text=k.replace('_',' ').title()).grid(row=i,column=0,sticky='w',padx=12,pady=5); e=ttk.Entry(win,width=42); e.grid(row=i,column=1,padx=8,pady=5); entries[k]=e
        entries['registration_date'].insert(0,date.today().isoformat()); entries['status'].insert(0,'ACTIVE')
        def save():
            d={k:e.get().strip() or None for k,e in entries.items()}
            try:
                for k in ('sno',):
                    if d[k]: d[k]=int(d[k])
                self.svc.add_member(self.user,d); messagebox.showinfo('Saved','Member registered.',parent=win); win.destroy(); self.show_main()
            except Exception as ex: messagebox.showerror('Cannot save',str(ex),parent=win)
        ttk.Button(win,text='Save member',command=save).grid(row=len(fields),column=1,sticky='e',pady=12)

    def circulation_tab(self):
        f=ttk.Frame(self.nb); self.nb.add(f,text='Issue / Return')
        # Keep Issue, Return and Transactions reachable on smaller screens.
        canvas=tk.Canvas(f,highlightthickness=0,background=self.palette['light'])
        vscroll=ttk.Scrollbar(f,orient='vertical',command=canvas.yview)
        canvas.configure(yscrollcommand=vscroll.set)
        vscroll.pack(side='right',fill='y'); canvas.pack(side='left',fill='both',expand=True)
        content=ttk.Frame(canvas,padding=18)
        content_window=canvas.create_window((0,0),window=content,anchor='nw')
        content.bind('<Configure>',lambda _e:canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',lambda e:canvas.itemconfigure(content_window,width=e.width))
        def _wheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), 'units')
        canvas.bind_all('<MouseWheel>',_wheel)
        f.bind('<Destroy>',lambda _e:canvas.unbind_all('<MouseWheel>'),add='+')
        ttk.Label(content,text='Book circulation',font=('Segoe UI',22,'bold')).pack(anchor='w',pady=(0,4))
        ttk.Label(content,text='Select a title and member. Verify the automatically displayed details, then confirm the transaction.',wraplength=1150).pack(anchor='w',pady=(0,12))

        issue=ttk.LabelFrame(content,text='Issue a book — confirmation required',padding=16); issue.pack(fill='x',pady=(0,12))
        issue.columnconfigure(1,weight=1); issue.columnconfigure(3,weight=1)
        ttk.Label(issue,text='Book name').grid(row=0,column=0,sticky='w',padx=6,pady=7)
        book_var=tk.StringVar(); book_box=ttk.Combobox(issue,textvariable=book_var,state='readonly',width=42); book_box.grid(row=0,column=1,sticky='ew',padx=6,pady=7)
        ttk.Label(issue,text='Member name').grid(row=0,column=2,sticky='w',padx=6,pady=7)
        member_var=tk.StringVar(); member_box=ttk.Combobox(issue,textvariable=member_var,state='readonly',width=42); member_box.grid(row=0,column=3,sticky='ew',padx=6,pady=7)
        ttk.Label(issue,text='Available physical copy').grid(row=1,column=0,sticky='w',padx=6,pady=7)
        copy_var=tk.StringVar(); copy_box=ttk.Combobox(issue,textvariable=copy_var,state='readonly',width=42); copy_box.grid(row=1,column=1,sticky='ew',padx=6,pady=7)
        ttk.Label(issue,text='Issue period (days)').grid(row=1,column=2,sticky='w',padx=6,pady=7)
        days=ttk.Combobox(issue,values=[7,15,21,28],state='readonly',width=12); days.set(15); days.grid(row=1,column=3,sticky='w',padx=6,pady=7)
        waitlist_var=tk.BooleanVar(value=False)
        ttk.Checkbutton(issue,text='If unavailable, add member to waiting list',variable=waitlist_var).grid(row=2,column=0,columnspan=4,sticky='w',padx=8,pady=4)

        detail=ttk.LabelFrame(issue,text='Issue details / verification',padding=12); detail.grid(row=3,column=0,columnspan=4,sticky='ew',padx=6,pady=10)
        detail.columnconfigure(1,weight=1); detail.columnconfigure(3,weight=1)
        labels={}
        for i,(key,label) in enumerate([('author','Author'),('isbn','ISBN'),('language','Language'),('location','Shelf location'),('member_id','Member ID'),('mobile','Mobile'),('status','Member status'),('due','Due date after issue')]):
            rr=i//2; cc=(i%2)*2
            ttk.Label(detail,text=label+':',font=('Segoe UI',11,'bold')).grid(row=rr,column=cc,sticky='w',padx=5,pady=4)
            labels[key]=ttk.Label(detail,text='—',foreground='#174a7e'); labels[key].grid(row=rr,column=cc+1,sticky='w',padx=5,pady=4)

        with self.db.connect() as c:
            books=[dict(r) for r in c.execute("SELECT id,title,author,isbn,language FROM books WHERE archived=0 ORDER BY title")]
            members=[dict(r) for r in c.execute("SELECT member_id,name,mobile,status FROM members ORDER BY name")]
        book_by_label={f"{b['title']}  [Book ID {b['id']}]":b for b in books}
        member_by_label={f"{m['name']}  [{m['member_id']}]":m for m in members}
        book_box['values']=list(book_by_label); member_box['values']=[k for k,v in member_by_label.items() if v['status']=='ACTIVE']
        copy_by_label={}

        def selected_book(): return book_by_label.get(book_var.get())
        def selected_member(): return member_by_label.get(member_var.get())
        def refresh_copies(*_):
            b=selected_book(); copy_by_label.clear(); copy_box.set('')
            if not b: copy_box['values']=[]; return
            with self.db.connect() as c:
                rows=c.execute("SELECT cp.accession_no,COALESCE(l.rack,'Unassigned') rack,COALESCE(l.shelf,'') shelf,COALESCE(l.compartment,'') compartment FROM book_copies cp LEFT JOIN locations l ON l.id=cp.location_id WHERE cp.book_id=? AND cp.status='AVAILABLE' ORDER BY cp.accession_no",(b['id'],)).fetchall()
            for r in rows:
                loc=' / '.join(x for x in (r['rack'],r['shelf'],r['compartment']) if x)
                text=f"{r['accession_no']} — {loc}"
                copy_by_label[text]=dict(r)
            copy_box['values']=list(copy_by_label)
            labels['author'].configure(text=b.get('author') or '—'); labels['isbn'].configure(text=b.get('isbn') or '—'); labels['language'].configure(text=b.get('language') or '—')
            labels['location'].configure(text='Select an available copy' if rows else 'NO AVAILABLE COPIES')
        def refresh_member(*_):
            m=selected_member()
            labels['member_id'].configure(text=m['member_id'] if m else '—')
            labels['mobile'].configure(text=m.get('mobile') or '—' if m else '—')
            labels['status'].configure(text=m['status'] if m else '—')
        def update_due(*_):
            from datetime import timedelta
            try: labels['due'].configure(text=(date.today()+timedelta(days=int(days.get()))).isoformat())
            except Exception: labels['due'].configure(text='—')
        def copy_changed(*_):
            cp=copy_by_label.get(copy_var.get())
            if cp:
                labels['location'].configure(text=' / '.join(x for x in (cp['rack'],cp['shelf'],cp['compartment']) if x))
        book_box.bind('<<ComboboxSelected>>',refresh_copies); member_box.bind('<<ComboboxSelected>>',refresh_member); copy_box.bind('<<ComboboxSelected>>',copy_changed); days.bind('<<ComboboxSelected>>',update_due)
        update_due()
        actions=ttk.Frame(issue); actions.grid(row=4,column=0,columnspan=4,sticky='ew',padx=6,pady=(4,0))
        def confirm_issue():
            b=selected_book(); m=selected_member(); cp=copy_by_label.get(copy_var.get())
            if not b: messagebox.showwarning('Select book','Please select a book name.',parent=self); return
            if not m: messagebox.showwarning('Select member','Please select an active member.',parent=self); return
            if not cp:
                if waitlist_var.get():
                    try:
                        self.svc.add_reservation(self.user,b['id'],m['member_id'])
                        messagebox.showinfo('Waiting list',f"{m['name']} has been added to the waiting list for '{b['title']}'. A notification will appear when a copy is returned.",parent=self)
                        self.show_main(); self.nb.select(3)
                    except Exception as ex: messagebox.showerror('Cannot add to waiting list',str(ex),parent=self)
                else: messagebox.showwarning('No available copies','No copy is available. Select the waiting-list option to reserve this title.',parent=self)
                return
            try: loan_days=int(days.get())
            except Exception: messagebox.showwarning('Issue period','Choose a valid issue period.',parent=self); return
            due=(date.today()).fromordinal(date.today().toordinal()+loan_days).isoformat()
            summary=(f"Book: {b['title']}\nAccession number: {cp['accession_no']}\nMember: {m['name']} ({m['member_id']})\n"
                     f"Issue period: {loan_days} days\nIssue date: {date.today().isoformat()}\nDue date: {due}\n\nConfirm issue of this physical copy?")
            if not messagebox.askyesno('Confirm book issue',summary,parent=self): return
            try:
                actual_due=self.svc.issue_book(self.user,cp['accession_no'],m['member_id'],loan_days)
                messagebox.showinfo('Book issued',f"'{b['title']}' issued to {m['name']}.\nAccession: {cp['accession_no']}\nDue date: {actual_due}\n\nThe copy has been marked ISSUED and removed from available shelf stock.",parent=self)
                self.show_main(); self.nb.select(3)
            except Exception as ex: messagebox.showerror('Issue failed',str(ex),parent=self)
        ttk.Button(actions,text='✓  Confirm & Issue Book',command=confirm_issue).pack(side='right')
        ttk.Button(actions,text='Clear selection',command=lambda:(book_var.set(''),member_var.set(''),copy_var.set(''),refresh_copies(),refresh_member())).pack(side='right',padx=8)

        ret=ttk.LabelFrame(content,text='Return a book — select member and issued book',padding=14); ret.pack(fill='x',pady=(0,12))
        ttk.Label(ret,text='Member name').grid(row=0,column=0,sticky='w',padx=6,pady=5)
        return_member_var=tk.StringVar(); return_member_box=ttk.Combobox(ret,textvariable=return_member_var,state='readonly',width=36); return_member_box.grid(row=0,column=1,padx=6,pady=5)
        ttk.Label(ret,text='Book currently held').grid(row=0,column=2,sticky='w',padx=6,pady=5)
        return_copy_var=tk.StringVar(); return_copy_box=ttk.Combobox(ret,textvariable=return_copy_var,state='readonly',width=58); return_copy_box.grid(row=0,column=3,padx=6,pady=5)
        with self.db.connect() as c:
            return_members=[dict(r) for r in c.execute("SELECT DISTINCT m.id,m.member_id,m.name FROM members m JOIN loans lo ON lo.member_id=m.id AND lo.status='ACTIVE' ORDER BY m.name")]
        return_member_by_label={f"{m['name']} [{m['member_id']}]":m for m in return_members}
        return_member_box['values']=list(return_member_by_label)
        return_copy_by_label={}
        def refresh_return_copies(*_):
            return_copy_by_label.clear(); return_copy_box.set('')
            m=return_member_by_label.get(return_member_var.get())
            if not m: return_copy_box['values']=[]; return
            with self.db.connect() as c:
                issued=c.execute("SELECT lo.id,cp.accession_no,b.title,lo.due_date FROM loans lo JOIN book_copies cp ON cp.id=lo.copy_id JOIN books b ON b.id=cp.book_id WHERE lo.member_id=? AND lo.status='ACTIVE' ORDER BY b.title,cp.accession_no",(m['id'],)).fetchall()
            for row in issued:
                label=f"{row['title']} — Accession {row['accession_no']} — Due {row['due_date']}"
                return_copy_by_label[label]=dict(row)
            return_copy_box['values']=list(return_copy_by_label)
        return_member_box.bind('<<ComboboxSelected>>',refresh_return_copies)
        def do_return():
            selected=return_copy_by_label.get(return_copy_var.get())
            if not selected:
                messagebox.showwarning('Select issued book','Choose a member and one of the books currently held by that member.',parent=self); return
            try:
                result=self.svc.return_book(self.user,selected['accession_no'])
                msg=f"Return recorded for {selected['title']}.\nOverdue days: {result['overdue_days']}\nCalculated penalty: ₹{result['penalty']:.2f}"
                if result['notified_member_id']:
                    msg+=f"\n\nWAITING-LIST NOTIFICATION\n{result['notified_member_name']} ({result['notified_member_id']}) has been notified that '{result['notified_book_title']}' is available."
                messagebox.showinfo('Return processed',msg,parent=self); self.show_main(); self.nb.select(3)
            except Exception as ex: messagebox.showerror('Return failed',str(ex),parent=self)
        ttk.Button(ret,text='Confirm return',command=do_return).grid(row=0,column=4,padx=8,pady=5)

        tx=ttk.LabelFrame(content,text='Circulation transactions — active issues and recent history',padding=10); tx.pack(fill='both',expand=True)
        txcols=('id','title','accession_no','member_id','member_name','issue_date','due_date','return_date','status','librarian')
        tx_tree=self._tree(tx,txcols,height=7)
        with self.db.connect() as c:
            rows=c.execute("SELECT lo.id,b.title,cp.accession_no,m.member_id,m.name member_name,lo.issue_date,lo.due_date,lo.return_date,lo.status,u.username librarian FROM loans lo JOIN book_copies cp ON cp.id=lo.copy_id JOIN books b ON b.id=cp.book_id JOIN members m ON m.id=lo.member_id JOIN users u ON u.id=lo.issued_by ORDER BY lo.id DESC LIMIT 300").fetchall()
        for r in rows: tx_tree.insert('','end',values=tuple(r[k] or '' for k in txcols))
        ttk.Label(content,text='Issue/return transactions are saved in the local database. Issuing changes the selected copy to ISSUED; returning changes it back to AVAILABLE.',wraplength=1100).pack(anchor='w',pady=(8,0))

    def password_tab(self):
        f=ttk.Frame(self.nb,padding=18); self.nb.add(f,text='Password Management')
        ttk.Label(f,text='Password management',font=('Segoe UI',22,'bold')).pack(anchor='w',pady=(0,4))
        ttk.Label(f,text='Passwords are stored as salted PBKDF2 hashes. Librarians can change their own password; only Admin can reset another account.',wraplength=1050).pack(anchor='w',pady=(0,16))
        panel=ttk.LabelFrame(f,text='Change password',padding=18); panel.pack(anchor='nw',fill='x')
        panel.columnconfigure(1,weight=1)
        fields={}
        if self.user['role']=='ADMIN':
            ttk.Label(panel,text='Account').grid(row=0,column=0,sticky='w',padx=8,pady=8)
            with self.db.connect() as c: usernames=[r['username'] for r in c.execute('SELECT username FROM users WHERE active=1 ORDER BY role,username')]
            target=tk.StringVar(value=self.user['username']); selector=ttk.Combobox(panel,textvariable=target,values=usernames,state='readonly',width=30); selector.grid(row=0,column=1,sticky='w',padx=8,pady=8)
        else:
            target=tk.StringVar(value=self.user['username'])
            ttk.Label(panel,text='Account').grid(row=0,column=0,sticky='w',padx=8,pady=8); ttk.Label(panel,text=self.user['username'],font=('Segoe UI',12,'bold')).grid(row=0,column=1,sticky='w',padx=8,pady=8)
        for row,(key,label) in enumerate([('new','New password'),('confirm','Confirm new password')],1):
            ttk.Label(panel,text=label).grid(row=row,column=0,sticky='w',padx=8,pady=8)
            e=ttk.Entry(panel,show='*',width=36); e.grid(row=row,column=1,sticky='w',padx=8,pady=8); fields[key]=e
        ttk.Label(panel,text='Minimum 10 characters. Choose a unique password and do not share it.',foreground='#555').grid(row=3,column=0,columnspan=2,sticky='w',padx=8,pady=8)
        def save_password():
            new=fields['new'].get(); confirm=fields['confirm'].get()
            if new!=confirm: messagebox.showerror('Password mismatch','The passwords do not match.',parent=self); return
            if len(new)<10: messagebox.showerror('Password too short','Password must contain at least 10 characters.',parent=self); return
            try:
                self.svc.change_password(self.user,target.get(),new)
                fields['new'].delete(0,'end'); fields['confirm'].delete(0,'end')
                messagebox.showinfo('Password updated',f"Password updated for {target.get()}.",parent=self)
            except Exception as ex: messagebox.showerror('Cannot update password',str(ex),parent=self)
        ttk.Button(panel,text='Update password',command=save_password).grid(row=4,column=1,sticky='w',padx=8,pady=12)

    def reports_tab(self):
        f=ttk.Frame(self.nb,padding=10); self.nb.add(f,text='Reports')
        selector=ttk.Frame(f); selector.pack(fill='x')
        report_names=['inventory','active_issues','overdue','waiting']; choice=tk.StringVar(value='inventory')
        ttk.Label(selector,text='Report').pack(side='left'); ttk.Combobox(selector,textvariable=choice,values=report_names,state='readonly',width=20).pack(side='left',padx=8)
        tree_holder=ttk.Frame(f); tree_holder.pack(fill='both',expand=True)
        current=[]
        def load():
            for w in tree_holder.winfo_children(): w.destroy()
            rows=self.svc.reports()['active_loans' if choice.get()=='active_issues' else choice.get()]; current.clear(); current.extend(rows)
            if rows:
                cols=tuple(rows[0].keys()); tree=self._tree(tree_holder,cols)
                for r in rows: tree.insert('','end',values=[r.get(k,'') if r.get(k) is not None else '' for k in cols])
            else: ttk.Label(tree_holder,text='No records found.').pack(pady=30)
        def export_excel():
            if not current: load()
            path=filedialog.asksaveasfilename(defaultextension='.xlsx',filetypes=[('Excel workbook','*.xlsx')])
            if path:
                try: export_xlsx(path,current,choice.get()); messagebox.showinfo('Exported',path)
                except Exception as ex: messagebox.showerror('Export failed',str(ex))
        def export_pdf_file():
            if not current: load()
            path=filedialog.asksaveasfilename(defaultextension='.pdf',filetypes=[('PDF','*.pdf')])
            if path:
                try: export_pdf(path,choice.get().replace('_',' ').replace('loans','issues').title(),current); messagebox.showinfo('Exported',path)
                except Exception as ex: messagebox.showerror('Export failed',str(ex))
        ttk.Button(selector,text='Refresh',command=load).pack(side='left'); ttk.Button(selector,text='Export Excel',command=export_excel).pack(side='right',padx=4); ttk.Button(selector,text='Export PDF',command=export_pdf_file).pack(side='right',padx=4); load()

    def admin_tab(self):
        f=ttk.Frame(self.nb,padding=16); self.nb.add(f,text='Admin & Backup')
        ttk.Label(f,text='Administrative settings',font=('Segoe UI',15,'bold')).pack(anchor='w',pady=8)
        rule=ttk.LabelFrame(f,text='Configure overdue penalty',padding=12); rule.pack(fill='x',pady=8)
        ttk.Label(rule,text='Rate per overdue day (₹)').grid(row=0,column=0,sticky='w',pady=4); rate=ttk.Entry(rule,width=16); rate.insert(0,'1'); rate.grid(row=0,column=1,padx=6)
        ttk.Label(rule,text='Effective from (YYYY-MM-DD)').grid(row=1,column=0,sticky='w',pady=4); eff=ttk.Entry(rule,width=16); eff.insert(0,date.today().isoformat()); eff.grid(row=1,column=1,padx=6)
        ttk.Label(rule,text='Grace days').grid(row=2,column=0,sticky='w',pady=4); grace=ttk.Entry(rule,width=16); grace.insert(0,'0'); grace.grid(row=2,column=1,padx=6)
        ttk.Label(rule,text='Maximum penalty (blank = no cap)').grid(row=3,column=0,sticky='w',pady=4); cap=ttk.Entry(rule,width=16); cap.grid(row=3,column=1,padx=6)
        def save_rule():
            try: self.svc.configure_penalty(self.user,float(rate.get()),eff.get(),int(grace.get()),float(cap.get()) if cap.get().strip() else None); messagebox.showinfo('Saved','Penalty rule saved with effective date.')
            except Exception as ex: messagebox.showerror('Cannot save rule',str(ex))
        ttk.Button(rule,text='Save penalty rule',command=save_rule).grid(row=4,column=1,sticky='e',pady=8)
        ttk.Label(f,text='Backups include the SQLite database. Keep the application closed during manual file copying where possible.').pack(anchor='w',pady=(16,4))
        def backup():
            dest=filedialog.asksaveasfilename(initialdir=APP_DIR/'backups',initialfile=f"library_backup_{date.today().isoformat()}.sqlite3",defaultextension='.sqlite3',filetypes=[('SQLite database','*.sqlite3')])
            if dest:
                try:
                    with self.db.connect() as src, sqlite3_connect(dest) as out: src.backup(out)
                    messagebox.showinfo('Backup complete',dest)
                except Exception as ex: messagebox.showerror('Backup failed',str(ex))
        ttk.Button(f,text='Create database backup',command=backup).pack(anchor='w')
        def restore():
            src=filedialog.askopenfilename(filetypes=[('SQLite database','*.sqlite3 *.db')])
            if not src: return
            if not messagebox.askyesno('Confirm restore','This replaces the current database. Create a backup first. Continue?'): return
            try:
                test=Database(src)
                with test.connect() as c: c.execute('PRAGMA integrity_check').fetchone()
                shutil.copy2(src,self.db.path); messagebox.showinfo('Restored','Database restored. The application will restart.'); self.show_login()
            except Exception as ex: messagebox.showerror('Restore failed',str(ex))
        ttk.Button(f,text='Restore database backup',command=restore).pack(anchor='w',pady=5)
        ttk.Label(f,text=f'Local data folder: {APP_DIR}',wraplength=800).pack(anchor='w',pady=10)

    def export_books(self):
        path=filedialog.asksaveasfilename(defaultextension='.xlsx',filetypes=[('Excel workbook','*.xlsx')],initialfile='books_export.xlsx')
        if not path: return
        rows=[]
        with self.db.connect() as c:
            records=c.execute("""SELECT b.title,b.author,b.publisher,b.edition,b.isbn,b.language,b.page_count,b.category,b.publication_year,b.cover_path,b.acquisition_date,b.source,b.cost,b.remarks,cp.accession_no,COALESCE(l.rack,'') rack,COALESCE(l.shelf,'') shelf,COALESCE(l.compartment,'') compartment
                FROM books b JOIN book_copies cp ON cp.book_id=b.id LEFT JOIN locations l ON l.id=cp.location_id WHERE b.archived=0 ORDER BY b.title,cp.accession_no""").fetchall()
            rows=[dict(r) for r in records]
        try:
            export_xlsx(path,rows,'Books')
            messagebox.showinfo('Books exported',f'Exported {len(rows)} physical-copy rows. This workbook uses the same column format accepted by Import books.\n\n{path}',parent=self)
        except Exception as ex: messagebox.showerror('Export failed',str(ex),parent=self)

    def delete_selected_book(self, tree):
        if self.user.get('role')!='ADMIN': messagebox.showerror('Permission denied','Only Admin can delete books.',parent=self); return
        selected=tree.selection()
        if not selected: messagebox.showwarning('Select book','Select a book row first.',parent=self); return
        values=tree.item(selected[0],'values'); book_id=int(values[0]); title=values[1]
        if not messagebox.askyesno('Confirm book deletion',f"Delete/archive '{title}'? Books with circulation history will be archived to preserve records.",parent=self): return
        try:
            result=self.svc.delete_book(self.user,book_id)
            messagebox.showinfo('Book removed',f"Book {result}.",parent=self); self.show_main()
        except Exception as ex: messagebox.showerror('Cannot delete book',str(ex),parent=self)

    def delete_selected_member(self, tree):
        if self.user.get('role')!='ADMIN': messagebox.showerror('Permission denied','Only Admin can delete members.',parent=self); return
        selected=tree.selection()
        if not selected: messagebox.showwarning('Select member','Select a member row first.',parent=self); return
        values=tree.item(selected[0],'values'); member_id=str(values[0]); name=str(values[2])
        if not messagebox.askyesno('Confirm member removal',f"Remove member '{name}' ({member_id})? Members with transaction/reservation/payment history will be deactivated to preserve records.",parent=self): return
        try:
            result=self.svc.delete_member(self.user,member_id)
            messagebox.showinfo('Member removed',f"Member {result}.",parent=self); self.show_main()
        except Exception as ex: messagebox.showerror('Cannot remove member',str(ex),parent=self)

    def import_books(self):
        path=filedialog.askopenfilename(filetypes=[('Excel / CSV','*.xlsx *.xls *.csv')])
        if not path:return
        try:
            rows=import_rows(path)
            if not rows: raise ValueError('No data rows found.')
            preview='\n'.join(f"Row {i+2}: {r.get('title','')} / accession {r.get('accession_no','')}" for i,r in enumerate(rows[:8]))
            if not messagebox.askyesno('Preview import',f'{len(rows)} rows found. First rows:\n\n{preview}\n\nContinue?'):return
            errors=[]; done=0
            # The exported workbook contains one row per physical copy. Group matching
            # title metadata so a round-trip import reconstructs one title with many copies.
            groups={}
            group_fields=('title','author','publisher','edition','isbn','language','page_count','category','publication_year','cover_path','acquisition_date','source','cost','remarks')
            for i,r in enumerate(rows,2):
                d={k:r.get(k) for k in BOOK_FIELDS if k in r}
                key=tuple(str(d.get(k) or '').strip().casefold() for k in group_fields)
                groups.setdefault(key,{'row_numbers':[],'data':{k:d.get(k) for k in group_fields},'copies':[]})
                groups[key]['row_numbers'].append(i)
                groups[key]['copies'].append({k:r.get(k) for k in ('accession_no','rack','shelf','compartment')})
            for group in groups.values():
                try:
                    d=group['data']
                    for k in ('page_count','publication_year'):
                        if d.get(k) not in (None,''): d[k]=int(float(d[k]))
                    if d.get('cost') not in (None,''): d['cost']=float(d['cost'])
                    self.svc.add_book(self.user,d,group['copies']); done+=len(group['copies'])
                except Exception as ex:
                    for idx,copy in zip(group['row_numbers'],group['copies']):
                        errors.append({'row':idx,'error':str(ex),'title':group['data'].get('title',''),'accession_no':copy.get('accession_no','')})
            if errors:
                p=filedialog.asksaveasfilename(defaultextension='.xlsx',filetypes=[('Excel','*.xlsx')],initialfile='book_import_errors.xlsx')
                if p: export_xlsx(p,errors,'Errors')
            messagebox.showinfo('Import complete',f'Imported: {done}\nErrors: {len(errors)}'+(f'\nError report: {p}' if errors and 'p' in locals() and p else ''))
            self.show_main()
        except Exception as ex: messagebox.showerror('Import failed',str(ex))

    def import_members(self):
        path=filedialog.askopenfilename(filetypes=[('Excel / CSV','*.xlsx *.xls *.csv')])
        if not path:return
        try:
            rows=import_rows(path); errors=[]; done=0
            if not messagebox.askyesno('Confirm import',f'Import {len(rows)} member rows? Existing records will not be overwritten.'):return
            for i,r in enumerate(rows,2):
                try:
                    d={k:r.get(k) for k in MEMBER_FIELDS if k in r}
                    if d.get('sno') not in (None,''): d['sno']=int(float(d['sno']))
                    self.svc.add_member(self.user,d); done+=1
                except Exception as ex: errors.append({'row':i,'error':str(ex),'member_id':r.get('member_id',''),'name':r.get('name','')})
            p=''
            if errors:
                p=filedialog.asksaveasfilename(defaultextension='.xlsx',initialfile='member_import_errors.xlsx',filetypes=[('Excel','*.xlsx')])
                if p: export_xlsx(p,errors,'Errors')
            messagebox.showinfo('Import complete',f'Imported: {done}\nErrors: {len(errors)}'); self.show_main()
        except Exception as ex: messagebox.showerror('Import failed',str(ex))

    def export_members(self):
        path=filedialog.asksaveasfilename(defaultextension='.xlsx',filetypes=[('Excel','*.xlsx')])
        if not path:return
        with self.db.connect() as c: rows=[dict(r) for r in c.execute('SELECT member_id,sno,name,father_name,address,registration_no,mobile,registration_date,status,remarks FROM members ORDER BY name')]
        try: export_xlsx(path,rows,'Members'); messagebox.showinfo('Exported',path)
        except Exception as ex: messagebox.showerror('Export failed',str(ex))

    def close_app(self):
        if messagebox.askyesno('Exit','Close the Library Management System?'): self.destroy()

def sqlite3_connect(path):
    import sqlite3
    c=sqlite3.connect(path); c.execute('PRAGMA foreign_keys=ON'); return c

def main(): LibraryApp().mainloop()
if __name__=='__main__': main()
