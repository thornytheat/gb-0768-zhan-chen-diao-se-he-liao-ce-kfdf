from collections import defaultdict
import unicodedata


def normalize(alias):
    return unicodedata.normalize('NFKC',alias).strip().casefold()


def identify(records, catalog):
    index=defaultdict(list)
    rejected=[]
    for row in catalog:
        fields=row['data']
        alias=normalize(fields['alias'])
        if not alias or not fields['lot'].strip() or not fields['pigment'].strip():
            rejected.append(row | {'code':'BAD_KEY'})
        else:
            index[alias].append(row)
    rows,isolated=[],[]
    for row in records:
        data=row['data']
        alias=normalize(data['lot'])
        inbound=data['action'] in {'OPEN','ISSUE'}
        transfer=data['action'] in {'POUR_OUT','POUR_IN'}
        contenders=index[alias] if inbound else []
        pairs={(r['data']['lot'],r['data']['pigment']) for r in contenders}
        base=row | {'lot_sources':contenders}
        if inbound and len(pairs)!=1:
            isolated.append(base | {'code':'LOT_CONFLICT' if pairs else 'LOT_UNKNOWN'})
        elif transfer:
            # 倒料行的 lot 栏是关联信息：出罐票记收罐罐号，收罐票记出罐票号。
            if not alias:
                isolated.append(base | {'code':'BAD_KEY'})
            else:
                rows.append(base | {'lot':None,'pigment':None})
        elif not inbound and alias:
            isolated.append(base | {'code':'MIXED_OUTPUT'})
        else:
            lot,pigment=next(iter(pairs)) if inbound else (None,None)
            rows.append(base | {'lot':lot,'pigment':pigment})
    return {'rows':rows,'isolated':isolated,'invalid_catalog':rejected}
