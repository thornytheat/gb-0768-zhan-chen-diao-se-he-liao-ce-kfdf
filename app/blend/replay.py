from collections import Counter, defaultdict

from app.blend.share import split_mass


def rebuild(records):
    balances=defaultdict(lambda:defaultdict(int))
    provenance=defaultdict(lambda:defaultdict(list))
    evidence,isolated=[],[]
    pours={}
    held=defaultdict(list)
    incoming=Counter(row['data']['pot'] for row in records if row['data']['action']=='POUR_IN')

    def deduct(row,stock,parts,extra=None):
        before=dict(stock)
        lines={lot:list(provenance[row['data']['pot']][lot]) for lot in parts}
        for lot,amount in parts.items():
            stock[lot]-=amount
            if stock[lot]==0:
                provenance[row['data']['pot']][lot].clear()
        evidence.append(row | {'before_mg':before,'parts_mg':parts,'after_mg':dict(stock),
                               'issue_lines':lines, **(extra or {})})

    def retry_held(pot):
        # 实收入账后，补足等实收的上件；仍缺料的继续等下一笔。
        queue,held[pot]=held[pot],[]
        for row in queue:
            stock=balances[pot]
            try:
                parts=split_mass(row['net_mg'],stock)
            except ValueError:
                held[pot].append(row)
                continue
            deduct(row,stock,parts,{'awaited':True})

    for row in records:
        fields=row['data']
        pot,action=fields['pot'],fields['action']
        stock=balances[pot]
        before=dict(stock)
        net=row['net_mg']
        if action in {'OPEN','ISSUE'}:
            parts={row['lot']:net}
            stock[row['lot']]+=net
            provenance[pot][row['lot']].append(row['line'])
        elif action=='POUR_OUT':
            # 出罐票当天入账：按出罐时点罐内成分扣减，快照即收罐成分的认定依据。
            target=fields['lot'].strip()
            if target==pot:
                isolated.append(row | {'code':'POUR_SELF','before_mg':before})
                continue
            try:
                parts=split_mass(net,stock)
            except ValueError as error:
                isolated.append(row | {'code':str(error),'before_mg':before})
                continue
            deduct(row,stock,parts,{'target_pot':target})
            pours[fields['ticket']]={'parts':parts,'target':target,'matched':False,
                                     'issue_lines':evidence[-1]['issue_lines']}
            continue
        elif action=='POUR_IN':
            incoming[pot]-=1
            link=fields['lot'].strip()
            pour=pours.get(link)
            if pour is None:
                isolated.append(row | {'code':'POUR_OUT_MISSING','before_mg':before})
                continue
            if pour['target']!=pot:
                isolated.append(row | {'code':'POUR_POT_MISMATCH','before_mg':before})
                continue
            if pour['matched']:
                isolated.append(row | {'code':'POUR_IN_DUPLICATE','before_mg':before})
                continue
            try:
                parts=split_mass(net,pour['parts'])
            except ValueError:
                isolated.append(row | {'code':'POUR_SURPLUS','before_mg':before})
                continue
            pour['matched']=True
            for lot,amount in parts.items():
                stock[lot]+=amount
                provenance[pot][lot].append(row['line'])
            shortage={lot:mass-parts.get(lot,0) for lot,mass in pour['parts'].items() if mass>parts.get(lot,0)}
            evidence.append(row | {'before_mg':before,'parts_mg':parts,'after_mg':dict(stock),
                                   'issue_lines':pour['issue_lines'],'out_ticket':link,
                                   'shortage_mg':shortage})
            retry_held(pot)
            continue
        else:
            try:
                parts=split_mass(net,stock)
            except ValueError as error:
                if action=='APPLY' and incoming[pot]>0:
                    # 收罐票未到：缺料的上件挂起，等实收补足再入账。
                    held[pot].append(row)
                else:
                    isolated.append(row | {'code':str(error),'before_mg':before})
                continue
            deduct(row,stock,parts)
            continue
        lines={lot: list(provenance[pot][lot]) for lot in parts}
        evidence.append(row | {'before_mg':before,'parts_mg':parts,'after_mg':dict(stock),'issue_lines':lines})
    for pot,queue in held.items():
        # 到封账仍无实收补足的上件，按超用隔离。
        isolated.extend(row | {'code':'OVERDRAW','before_mg':dict(balances[pot])} for row in queue)
    pending={pot:{lot:mass for lot,mass in stock.items() if mass} for pot,stock in balances.items()}
    return {'rows':evidence,'isolated':isolated,'pending_mg':pending}
