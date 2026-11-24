def reconcile(recovery):
    # 倒料对账：每笔出罐票对照其实收，短少按出罐成分拆到批号。
    inbound={}
    for row in recovery['rows']:
        if row['data']['action']=='POUR_IN':
            inbound[row['out_ticket']]=row
    pours,awaited=[],[]
    for row in recovery['rows']:
        action=row['data']['action']
        if action=='POUR_OUT':
            fields=row['data']
            entry={'out_ticket':fields['ticket'],'source_pot':fields['pot'],'target_pot':row['target_pot'],
                   'at':row['at'],'issued_mg':row['net_mg'],'issued_parts':row['parts_mg'],
                   'in_ticket':None,'received_at':None,'received_mg':None,'received_parts':None,
                   'shortage_mg':None,'code':'IN_TRANSIT'}
            received=inbound.get(fields['ticket'])
            if received is not None:
                entry.update(in_ticket=received['data']['ticket'],received_at=received['at'],
                             received_mg=received['net_mg'],received_parts=received['parts_mg'],
                             shortage_mg=received['shortage_mg'],delay=received['delay'],
                             code='SHORT' if received['shortage_mg'] else 'MATCH')
            pours.append(entry)
        elif row.get('awaited'):
            awaited.append(row)
    isolated=[row for row in recovery['isolated'] if row['data']['action'] in {'POUR_OUT','POUR_IN'}]
    return {'pours':pours,'awaited':awaited,'isolated':isolated}
