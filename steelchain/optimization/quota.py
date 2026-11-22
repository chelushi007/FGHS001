import sqlite3
from pathlib import Path

def migrate_quota_ledger(db_path):
    con=sqlite3.connect(db_path); con.execute('PRAGMA foreign_keys=ON')
    sql=(Path(__file__).resolve().parents[2]/'migrations'/'002_quota_ledger.sql').read_text(encoding='utf-8-sig')
    con.executescript(sql); con.commit(); con.close()

def reserve_quota(db_path, party_id, year, transaction_key, amount):
    """Idempotently reserve simulated individual quota; duplicate keys never double count."""
    migrate_quota_ledger(db_path); con=sqlite3.connect(db_path,timeout=10); con.execute('BEGIN IMMEDIATE')
    prior=con.execute('SELECT state,amount FROM quota_ledger WHERE transaction_key=?',(transaction_key,)).fetchone()
    if prior:
        con.rollback(); con.close()
        if prior[1] != amount: raise ValueError('idempotency key reused with different amount')
        return {'state':prior[0],'duplicate':True}
    role=con.execute('SELECT role FROM parties WHERE id=?',(party_id,)).fetchone()
    if not role or role[0]!='INDIVIDUAL': con.rollback(); con.close(); raise ValueError('quota applies only to individual sellers')
    account=con.execute('SELECT limit_amount,used_amount,reserved_amount FROM quotas WHERE party_id=? AND year=?',(party_id,year)).fetchone()
    if not account: con.rollback(); con.close(); raise ValueError('quota account missing for year')
    if account[1]+account[2]+amount>account[0]: con.rollback(); con.close(); raise ValueError('annual simulated quota exceeded')
    con.execute('UPDATE quotas SET reserved_amount=reserved_amount+? WHERE party_id=? AND year=?',(amount,party_id,year))
    con.execute("INSERT INTO quota_ledger(party_id,year,transaction_key,amount,state) VALUES(?,?,?,?,'RESERVED')",(party_id,year,transaction_key,amount))
    con.commit(); con.close(); return {'state':'RESERVED','duplicate':False}

def settle_quota(db_path, transaction_key):
    _transition(db_path,transaction_key,'RESERVED','SETTLED')
def release_quota(db_path, transaction_key):
    _transition(db_path,transaction_key,'RESERVED','RELEASED')
def _transition(db_path,key,expected,target):
    con=sqlite3.connect(db_path,timeout=10); con.execute('BEGIN IMMEDIATE')
    row=con.execute('SELECT party_id,year,amount,state FROM quota_ledger WHERE transaction_key=?',(key,)).fetchone()
    if not row: con.rollback(); con.close(); raise ValueError('quota reservation not found')
    pid,year,amount,state=row
    if state==target: con.rollback(); con.close(); return
    if state!=expected: con.rollback(); con.close(); raise ValueError(f'invalid quota transition {state}->{target}')
    if target=='SETTLED': con.execute('UPDATE quotas SET reserved_amount=reserved_amount-?,used_amount=used_amount+? WHERE party_id=? AND year=?',(amount,amount,pid,year))
    else: con.execute('UPDATE quotas SET reserved_amount=reserved_amount-? WHERE party_id=? AND year=?',(amount,pid,year))
    con.execute('UPDATE quota_ledger SET state=? WHERE transaction_key=?',(target,key)); con.commit(); con.close()
