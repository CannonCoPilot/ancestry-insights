# Phase 3: External Enrichment Coverage Report

**Generated**: 2026-03-26T03:17:13.344811

---

## Column Coverage

| Column | Non-NULL | % Coverage |
|--------|---------|-----------|
| gdp_per_capita_ppp | 199 | 82.9% |
| internet_pct | 185 | 77.1% |
| mobile_per_100 | 210 | 87.5% |
| tertiary_enrollment | 147 | 61.3% |
| population | 215 | 89.6% |
| hdi | 193 | 80.4% |
| education_index | 193 | 80.4% |
| life_expectancy | 193 | 80.4% |
| lds_membership | 145 | 60.4% |
| lds_congregations | 145 | 60.4% |
| lds_temples | 50 | 20.8% |
| lds_stakes | 86 | 35.8% |
| lds_members_per_capita | 138 | 57.5% |
| gepi | 186 | 77.5% |

## User-Level Coverage

How many FamilySearch users can be enriched?


| Metric | Count | % of 7,625,105 users |
|--------|-------|---------|
| Has any enrichment | 7,621,781 | 100.0% |

## Deferred Sources

| Source | Reason | Impact |
|--------|--------|--------|
| Pew Religiosity | Requires free account + SPSS download | 36-country coverage only |
| Google Trends | pytrends archived; official API closed-alpha | Genealogy interest proxy unavailable |
| ITU IDI | Excel download may have changed format | WDI internet_pct used as substitute |