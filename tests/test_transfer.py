import json

from app.job import MixingJob

JOB=json.dumps({'order':'T-9','start':'2026-11-08T08:00:00+08:00',
                'end':'2026-11-08T18:00:00+08:00','cutoff':'2026-11-08T22:00:00+08:00'})
TARES=('container,version,start,end,mass,unit\n'
       'TIN-A,TA1,2026-11-08T08:00:00+08:00,2026-11-08T18:00:00+08:00,20,g\n'
       'TIN-B,TB1,2026-11-08T08:00:00+08:00,2026-11-08T18:00:00+08:00,10,g')
LOTS='alias,lot,pigment\n胭脂,R-017,铁红\n石白,W-041,钛白\n青,B-003,群青'
HEAD='ticket,pot,container,action,lot,gross,unit,occurred,received'
T='2026-11-08T{}:00:00+08:00'


def pour_job(*lines):
    files={'job':JOB,'weights':HEAD+'\n'+'\n'.join(lines),'tares':TARES,'lots':LOTS,
           'claims':'lot,mass,unit,receipt'}
    return MixingJob(files)


def row(job,ticket):
    return next(r for r in job.recovery['rows'] if r['data']['ticket']==ticket)


def test_pour_out_deducts_source_on_out_day(pour):
    # 出罐票当天入账：原罐不再多出可用料。
    out=row(pour,'0101')
    assert out['parts_mg']=={'R-017':30000,'W-041':60000}
    assert out['after_mg']=={'R-017':70000,'W-041':140000}


def test_receive_books_actual_receipt_not_issued_amount(pour):
    # 收罐按实收入账，不按出罐量预加。
    received=row(pour,'0102')
    assert (received['net_mg'],received['parts_mg'])==(60000,{'R-017':20000,'W-041':40000})
    assert received['delay']


def test_shortage_named_by_lot(pour):
    # 实收少于实发：对账说清短少的批号。
    entry=next(p for p in pour.transfer['pours'] if p['out_ticket']=='0101')
    assert entry['code']=='SHORT'
    assert entry['shortage_mg']=={'R-017':10000,'W-041':20000}
    assert entry['issued_mg']-entry['received_mg']==sum(entry['shortage_mg'].values())


def test_late_receipt_keeps_out_event_composition(pour):
    # 原罐在收票到达前补进青(B-003)，收料成分仍认出罐那次。
    received=row(pour,'0102')
    assert set(received['parts_mg'])=={'R-017','W-041'}
    assert received['issue_lines']==row(pour,'0101')['issue_lines']


def test_short_apply_waits_for_receipt_then_books(pour):
    # 缺料的上件等实收补足再入账。
    apply=row(pour,'0005')
    assert apply['awaited'] and apply['before_mg']=={'B-003':60000,'R-017':20000,'W-041':40000}
    assert apply['parts_mg']=={'B-003':50000,'R-017':16667,'W-041':33333}
    assert [r['data']['ticket'] for r in pour.transfer['awaited']]==['0005']


def test_covered_apply_books_without_waiting():
    # 收罐有余料的上件照常核料，不等收罐票。
    job=pour_job(f'0001,A12,TIN-A,OPEN,胭脂,120,g,{T.format("08")},{T.format("08")}',
                 f'0002,B08,TIN-B,ISSUE,青,70,g,{T.format("08")},{T.format("08")}',
                 f'0101,A12,TIN-A,POUR_OUT,B08,60,g,{T.format("10")},{T.format("10")}',
                 f'0003,B08,TIN-B,APPLY,,40,g,{T.format("11")},{T.format("11")}',
                 f'0102,B08,TIN-B,POUR_IN,0101,50,g,{T.format("14")},{T.format("20")}')
    apply=row(job,'0003')
    assert 'awaited' not in apply and apply['parts_mg']=={'B-003':30000}
    assert job.transfer['awaited']==[]


def test_retried_receipt_is_not_booked_twice(pour):
    # 同一张收罐票重试不重复入账。
    assert [(r['data']['ticket'],r['code']) for r in pour.weighings['isolated']]==[('0102','TICKET_DUPLICATE')]
    assert pour.balance['totals']['poured_in_mg']==60000


def test_unreceived_pour_stays_in_transit(pour):
    entry=next(p for p in pour.transfer['pours'] if p['out_ticket']=='0103')
    assert (entry['code'],entry['received_mg'])==('IN_TRANSIT',None)
    assert entry['issued_parts']=={'R-017':7000,'W-041':14000,'B-003':5000}
    assert pour.recovery['pending_mg']['B08']=={'B-003':10000,'R-017':3333,'W-041':6667}


def test_pour_conservation(pour):
    totals=pour.balance['totals']
    assert all(r['check_mg']==0 for r in pour.balance['lines'])
    assert (totals['opening_mg']+totals['issued_mg']+totals['poured_in_mg']
            ==totals['applied_mg']+totals['loss_mg']+totals['returned_mg']
              +totals['poured_out_mg']+totals['disputed_mg'])


def test_orphan_receive_ticket_isolated():
    job=pour_job(f'0001,B08,TIN-B,ISSUE,青,70,g,{T.format("08")},{T.format("08")}',
                 f'0102,B08,TIN-B,POUR_IN,9999,50,g,{T.format("14")},{T.format("20")}')
    assert [(r['data']['ticket'],r['code']) for r in job.recovery['isolated']]==[('0102','POUR_OUT_MISSING')]
    assert job.transfer['pours']==[]


def test_over_received_ticket_isolated():
    job=pour_job(f'0001,A12,TIN-A,OPEN,胭脂,120,g,{T.format("08")},{T.format("08")}',
                 f'0101,A12,TIN-A,POUR_OUT,B08,60,g,{T.format("10")},{T.format("10")}',
                 f'0102,B08,TIN-B,POUR_IN,0101,70,g,{T.format("14")},{T.format("20")}')
    assert [(r['data']['ticket'],r['code']) for r in job.recovery['isolated']]==[('0102','POUR_SURPLUS')]
    assert job.transfer['pours'][0]['code']=='IN_TRANSIT'


def test_second_receive_ticket_for_same_pour_isolated():
    job=pour_job(f'0001,A12,TIN-A,OPEN,胭脂,120,g,{T.format("08")},{T.format("08")}',
                 f'0101,A12,TIN-A,POUR_OUT,B08,60,g,{T.format("10")},{T.format("10")}',
                 f'0102,B08,TIN-B,POUR_IN,0101,50,g,{T.format("14")},{T.format("20")}',
                 f'0103,B08,TIN-B,POUR_IN,0101,50,g,{T.format("15")},{T.format("21")}')
    assert row(job,'0102')['parts_mg']=={'R-017':40000}
    assert [(r['data']['ticket'],r['code']) for r in job.recovery['isolated']]==[('0103','POUR_IN_DUPLICATE')]
    assert job.balance['totals']['poured_in_mg']==40000


def test_wrong_pot_receive_isolated():
    job=pour_job(f'0001,A12,TIN-A,OPEN,胭脂,120,g,{T.format("08")},{T.format("08")}',
                 f'0101,A12,TIN-A,POUR_OUT,B08,60,g,{T.format("10")},{T.format("10")}',
                 f'0102,A12,TIN-A,POUR_IN,0101,50,g,{T.format("14")},{T.format("20")}')
    assert [(r['data']['ticket'],r['code']) for r in job.recovery['isolated']]==[('0102','POUR_POT_MISMATCH')]


def test_self_pour_isolated():
    job=pour_job(f'0001,A12,TIN-A,OPEN,胭脂,120,g,{T.format("08")},{T.format("08")}',
                 f'0101,A12,TIN-A,POUR_OUT,A12,60,g,{T.format("10")},{T.format("10")}')
    assert [(r['data']['ticket'],r['code']) for r in job.recovery['isolated']]==[('0101','POUR_SELF')]


def test_apply_never_covered_is_isolated_overdraw():
    job=pour_job(f'0001,A12,TIN-A,OPEN,胭脂,120,g,{T.format("08")},{T.format("08")}',
                 f'0002,B08,TIN-B,ISSUE,青,40,g,{T.format("08")},{T.format("08")}',
                 f'0101,A12,TIN-A,POUR_OUT,B08,40,g,{T.format("10")},{T.format("10")}',
                 f'0003,B08,TIN-B,APPLY,,60,g,{T.format("11")},{T.format("11")}',
                 f'0102,B08,TIN-B,POUR_IN,0101,25,g,{T.format("14")},{T.format("20")}')
    assert [(r['data']['ticket'],r['code']) for r in job.recovery['isolated']]==[('0003','OVERDRAW')]
    assert job.transfer['awaited']==[]


def test_transfer_page_and_export(client):
    page=client.get('/studio/transfer?sample=pour')
    assert page.status_code==200 and '倒料对账' in page.get_data(as_text=True)
    key=client.post('/api/books',json={'sample':'pour'}).json['key']
    doc=client.get('/api/export/'+key).json
    assert doc['mass_check_mg']==0
    pours=doc['snapshot']['transfer']['pours']
    assert [(p['out_ticket'],p['code']) for p in pours]==[('0101','SHORT'),('0103','IN_TRANSIT')]
