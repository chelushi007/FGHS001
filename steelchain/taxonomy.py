from pathlib import Path
import sqlite3
TAXONOMY=[('废钢类','重废类','优质重废'),('废钢类','重废类','重废'),('废钢类','中轻废类','中重废'),('废钢类','中轻废类','中废'),('废钢类','中轻废类','剪切料'),('废钢类','中轻废类','轻废'),('废钢类','颗粒/特殊成型料','钢筋切粒'),('废钢类','颗粒/特殊成型料','马蹄铁'),('废钢类','颗粒/特殊成型料','破碎废钢'),('废钢类','打包料类','优质碳钢打包料'),('废钢类','打包料类','三级打包料'),('废钢类','打包料类','四级打包料'),('废钢类','铁屑类','钢屑/铁屑'),('废钢类','大件毛料','优质重废毛料'),('废钢类','大件毛料','重废毛料'),('废钢类','大件毛料','中废毛料'),('废钢类','型材/建筑毛料','架子管毛料'),('废钢类','混杂毛料','剪切毛料'),('废钢类','混杂毛料','统料毛料'),('废钢类','混杂毛料','彩涂毛料'),('废钢类','不锈钢系列','不锈钢304'),('废钢类','不锈钢系列','不锈钢316'),('废钢类','其他合金钢','合金钢废钢')]
def migrate_and_seed(db_path):
 con=sqlite3.connect(db_path); con.execute('PRAGMA foreign_keys=ON')
 sql=(Path(__file__).resolve().parents[1]/'migrations'/'003_scrap_taxonomy.sql').read_text(encoding='utf-8-sig'); con.executescript(sql)
 con.executemany('INSERT OR IGNORE INTO scrap_taxonomy(level1,level2,level3) VALUES(?,?,?)',TAXONOMY)
 tax={x[0]:x[1] for x in con.execute('SELECT level3,id FROM scrap_taxonomy')}
 proposals={'重型废钢':'重废','中型废钢':'中重废','小型废钢':'轻废','统料废钢':'统料毛料','钢筋切头':'钢筋切粒','钢筋压块':'三级打包料','工业边角料':'剪切毛料','冷轧料':'优质碳钢打包料','热轧料':'优质碳钢打包料','炉料':'优质重废','钢刨花':'钢屑/铁屑','铁屑':'钢屑/铁屑','铸钢件':'重废毛料','废钢筋':'重废','汽车拆解料':'统料毛料','船板料':'优质重废毛料','优质废钢':'优质重废','破碎料':'破碎废钢','生铁':'合金钢废钢'}
 for cid,name in con.execute('SELECT id,name FROM categories'):
  if name in tax: con.execute("INSERT OR REPLACE INTO category_taxonomy_map VALUES(?,?,'EXACT','名称完全一致','SIMULATED')",(cid,tax[name]))
  elif proposals.get(name) in tax: con.execute("INSERT OR REPLACE INTO category_taxonomy_map VALUES(?,?,'REVIEW_REQUIRED','候选映射，须业务审核后方可用于交易过滤','SIMULATED')",(cid,tax[proposals[name]]))
  else: con.execute("INSERT OR REPLACE INTO category_taxonomy_map VALUES(?,NULL,'UNMAPPED','没有候选映射，须业务确认','SIMULATED')",(cid,))
 con.commit(); result={'taxonomy_leaves':con.execute('SELECT COUNT(*) FROM scrap_taxonomy').fetchone()[0],'exact_mappings':con.execute("SELECT COUNT(*) FROM category_taxonomy_map WHERE mapping_status='EXACT'").fetchone()[0],'review_required':con.execute("SELECT COUNT(*) FROM category_taxonomy_map WHERE mapping_status='REVIEW_REQUIRED'").fetchone()[0],'unmapped':con.execute("SELECT COUNT(*) FROM category_taxonomy_map WHERE mapping_status='UNMAPPED'").fetchone()[0]}; con.close(); return result
