"""Offline, one-time experiment reset. Market memory and provider reservations survive."""
from .store import INITIAL,now

def reset_experiment(store,start_at,reset_id):
    row=store.db.execute("SELECT value FROM state WHERE key='reset_id'").fetchone()
    if row and store.get('reset_id')==reset_id:return False
    store.db.execute('BEGIN IMMEDIATE')
    try:
        for table in ('positions','position_plans','trades','notes','decisions','equity','research','history_retention'):
            store.db.execute('DELETE FROM '+table)
        store.db.execute("DELETE FROM state WHERE key LIKE 'exit_%' OR key='next_research'")
        state={'cash':INITIAL,'status':'running','strategy':'AI choosing strategy','strategy_why':'Fresh experiment with simulated capital','strategy_horizon':'Undecided','plan':None,'plan_version':0,'last_plan':'','last_reflection':'','last_cycle':0,'last_error':'','start_not_before':start_at,'phase':'Scheduled · fresh experiment starts at market open','reset_id':reset_id}
        for key,value in state.items():store.set(key,value)
        store.db.execute('INSERT INTO equity(ts,equity,cash) VALUES (?,?,?)',(now(),INITIAL,INITIAL))
        store.db.execute('COMMIT');return True
    except BaseException:store.db.execute('ROLLBACK');raise
