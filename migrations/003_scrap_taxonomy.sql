CREATE TABLE IF NOT EXISTS scrap_taxonomy(
 id INTEGER PRIMARY KEY,
 level1 TEXT NOT NULL,
 level2 TEXT NOT NULL,
 level3 TEXT NOT NULL,
 data_origin TEXT NOT NULL DEFAULT 'SIMULATED',
 UNIQUE(level1,level2,level3)
);
CREATE TABLE IF NOT EXISTS category_taxonomy_map(
 category_id INTEGER PRIMARY KEY REFERENCES categories(id),
 taxonomy_id INTEGER REFERENCES scrap_taxonomy(id),
 mapping_status TEXT NOT NULL CHECK(mapping_status IN ('EXACT','REVIEW_REQUIRED','UNMAPPED')),
 note TEXT NOT NULL DEFAULT '',
 data_origin TEXT NOT NULL DEFAULT 'SIMULATED'
);
