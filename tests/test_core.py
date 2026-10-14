from datetime import date, timedelta
import pytest
from library_app.db import Database
from library_app.services import LibraryService, LibraryError

@pytest.fixture
def setup(tmp_path):
    db=Database(tmp_path/'test.sqlite3'); svc=LibraryService(db)
    svc.bootstrap_users('AdminPass!123',['LibrarianPass!1','LibrarianPass!2','LibrarianPass!3','LibrarianPass!4'])
    admin=svc.authenticate('admin','AdminPass!123'); librarian=svc.authenticate('librarian1','LibrarianPass!1')
    return db,svc,admin,librarian

def test_bootstrap_exact_accounts_and_auth(setup):
    db,svc,admin,lib=setup
    assert admin['role']=='ADMIN' and lib['role']=='LIBRARIAN'
    with db.connect() as c: assert c.execute('SELECT COUNT(*) FROM users').fetchone()[0]==5
    assert svc.authenticate('admin','wrong') is None

def test_admin_permission_enforced(setup):
    _,svc,admin,lib=setup
    with pytest.raises(PermissionError): svc.configure_penalty(lib,2)

def test_issue_return_and_availability(setup):
    db,svc,admin,lib=setup
    svc.add_member(admin,{'member_id':'M001','name':'Test Member','status':'ACTIVE'})
    svc.add_book(admin,{'title':'Test Book'},[{'accession_no':'A001','rack':'R1','shelf':'S1'}])
    due=svc.issue_book(lib,'A001','M001',7,'2026-01-01')
    assert due=='2026-01-08'
    with pytest.raises(LibraryError): svc.issue_book(lib,'A001','M001',7,'2026-01-02')
    result=svc.return_book(lib,'A001','2026-01-10')
    assert result['overdue_days']==2
    assert svc.search_books('Test Bok')[0]['available_copies']==1

def test_penalty_effective_date_and_grace(setup):
    _,svc,admin,lib=setup
    svc.add_member(admin,{'member_id':'M001','name':'Test Member'})
    svc.add_book(admin,{'title':'Test Book'},[{'accession_no':'A001'}])
    svc.configure_penalty(admin,5,'2026-01-01',grace_days=1)
    svc.issue_book(lib,'A001','M001',7,'2026-01-01')
    result=svc.return_book(lib,'A001','2026-01-11')
    assert result['overdue_days']==3 and result['penalty']==10.0

def test_duplicate_accession_rejected(setup):
    _,svc,admin,_=setup
    svc.add_book(admin,{'title':'One'},[{'accession_no':'DUP'}])
    with pytest.raises(Exception): svc.add_book(admin,{'title':'Two'},[{'accession_no':'DUP'}])

def test_inactive_member_cannot_borrow(setup):
    _,svc,admin,lib=setup
    svc.add_member(admin,{'member_id':'M002','name':'Inactive','status':'INACTIVE'})
    svc.add_book(admin,{'title':'Test'},[{'accession_no':'A002'}])
    with pytest.raises(LibraryError): svc.issue_book(lib,'A002','M002')

def test_member_cannot_hold_more_than_two_books(setup):
    db,svc,admin,lib=setup
    svc.add_member(admin,{'member_id':'M003','name':'Three Book Test'})
    svc.add_book(admin,{'title':'Book One'},[{'accession_no':'B001'}])
    svc.add_book(admin,{'title':'Book Two'},[{'accession_no':'B002'}])
    svc.add_book(admin,{'title':'Book Three'},[{'accession_no':'B003'}])
    svc.issue_book(lib,'B001','M003',7)
    svc.issue_book(lib,'B002','M003',7)
    with pytest.raises(LibraryError,match='maximum of 2'):
        svc.issue_book(lib,'B003','M003',7)

def test_waitlist_added_when_unavailable_and_return_notifies(setup):
    db,svc,admin,lib=setup
    svc.add_member(admin,{'member_id':'M004','name':'First Member'})
    svc.add_member(admin,{'member_id':'M005','name':'Waiting Member'})
    book_id=svc.add_book(admin,{'title':'Reserved Title'},[{'accession_no':'R001'}])
    svc.issue_book(lib,'R001','M004',7)
    # A reservation can be created once no physical copy remains available.
    svc.add_reservation(lib,book_id,'M005')
    result=svc.return_book(lib,'R001')
    assert result['notified_member_id']=='M005'
    assert result['notified_member_name']=='Waiting Member'

def test_admin_only_delete_member_and_book(setup):
    db,svc,admin,lib=setup
    svc.add_member(admin,{'member_id':'M006','name':'Delete Test'})
    book_id=svc.add_book(admin,{'title':'Delete Book'},[{'accession_no':'DEL001'}])
    with pytest.raises(PermissionError): svc.delete_member(lib,'M006')
    with pytest.raises(PermissionError): svc.delete_book(lib,book_id)
    assert svc.delete_member(admin,'M006')=='deleted'
    assert svc.delete_book(admin,book_id)=='deleted'
