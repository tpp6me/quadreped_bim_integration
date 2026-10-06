import json
import os
from pathlib import Path
import sqlite3
from datetime import datetime, timezone
import uuid

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data'
DB=Path(os.environ.get('FIELDLINK_DB',str(DATA/'fieldlink.sqlite')))
def now():return datetime.now(timezone.utc).isoformat()
def connect():
    conn=sqlite3.connect(DB,timeout=10);conn.row_factory=sqlite3.Row;return conn
def save(conn,table,record):conn.execute(f'INSERT OR REPLACE INTO {table}(id,payload) VALUES (?,?)',(record['id'],json.dumps(record)))
def all_records(table):
    with connect() as conn:return [json.loads(r['payload']) for r in conn.execute(f'SELECT payload FROM {table} ORDER BY rowid')]
def get(conn,table,key):
    row=conn.execute(f'SELECT payload FROM {table} WHERE id=?',(key,)).fetchone()
    return json.loads(row['payload']) if row else None
def seed():
    DB.parent.mkdir(exist_ok=True,parents=True)
    with connect() as conn:
        for table in ['observations','issues','exports','analyses']:conn.execute(f'CREATE TABLE IF NOT EXISTS {table}(id TEXT PRIMARY KEY,payload TEXT NOT NULL)')
        if conn.execute('SELECT COUNT(*) FROM observations').fetchone()[0]:return
        entries=[
            ('OBS-001','Cable across floor area','v10',102,'storage','Site Safety','Medium','A dark cable is visible across the floor in front of stored materials. Review the route and access requirements before deciding whether it needs protection or relocation.',['cables on floor','cable','access','walkway','marked aisle'],'The visible cable and surrounding route are clear; use and access requirements are unknown.'),
            ('OBS-002','Visible floor staining','v02',105,'production','General','Medium','Dark patches are visible on the floor beside the production equipment. Their material, cause, and whether the surface is wet cannot be determined from this image.',['floor staining','floor condition','production','inspection'],'Appearance alone does not establish a spill or slip hazard.'),
            ('OBS-003','Storage rack evidence','v06',85,'rack-1','General','Low','Racks and stored materials are visible on both sides of the route. This frame documents the observed storage arrangement for a follow-up walkdown.',['storage racks','warehouse','stored materials','inventory'],'Individual rack identity and loading capacity are not verified.'),
            ('OBS-004','Materials beside an aisle','v05',60,'loading','General','Low','Wrapped components and packaging are visible alongside the marked route. Review whether the current staging arrangement matches the intended handover layout.',['staged materials','packaging','marked aisle','pallets'],'Model location is illustrative; this does not establish a clearance violation.'),
            ('OBS-005','Installed equipment reference','v02',60,'machine-1','MEP','Low','Enclosed production equipment is visible beside the marked aisle. Use this capture as an equipment evidence reference; operational testing and acceptance are separate records.',['installed equipment','machine','production','marked aisle'],'The representative equipment ID is manually assigned and is not a verified factory asset identity.'),
            ('OBS-006','Assembly area reference','v09',35,'assembly','General','Low','Assembly benches, containers, and green floor surfacing are visible. This provides a visual record of the area for the handover scenario.',['assembly area','workstation','installed equipment','green floor'],'This image does not prove commissioning, installation date, or completion of the work package.')
        ]
        for key,title,video,time,element,discipline,priority,description,tags,limit in entries:
            save(conn,'observations',{'id':key,'title':title,'videoId':video,'timestamp':time,'start':max(0,time-5),'end':time+5,'elementId':element,'discipline':discipline,'priority':priority,'description':description,'tags':tags,'limitations':limit,'status':'suggested','authoring':'Curated from sampled frames','reviewer':None,'reviewedAt':None,'thumbnail':f'/assets-data/frames/{video}/{time:03}.jpg','evidence':f'/assets-data/evidence/{key}.jpg','revision':1,'history':[]})
