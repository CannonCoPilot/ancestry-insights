# FamilySearch Data Scientist 2 — Initial Research Report

## 1. Assignment Summary

**Title:** Exercise: Machine Learning User Segmentation

**Goal:** Analyze newly created FamilySearch user accounts (all created within the past year) and build an ML segmentation model that groups users by early behaviors, demographics, and contribution patterns.

**Key emphasis from the prompt:** They care more about *thinking process, framing, feature engineering, and communication* than algorithmic perfection. They explicitly say there is no "correct" answer.

### Required Deliverables (4 sections)

| # | Deliverable | What They Want |
|---|-------------|----------------|
| 1 | **Workflow** | Up-front plan: goal interpretation, question priorities, workflow description, assumptions, risks/edge cases, reproducibility approach |
| 2 | **EDA** | Summary stats, distributions, activity patterns, demographics, missing data/biases, engagement-contribution relationships |
| 3 | **Modeling** | ML segmentation (any technique): rationale, feature engineering, number-of-segments evaluation, cluster validation, segment descriptions |
| 4 | **Insights & Recommendations** | Business-oriented findings for senior leaders: segment differentiation, high-potential segments, behavioral patterns, onboarding/product recommendations, surprising findings |

---

## 2. Data Overview

### File Stats
- **File:** `Data Scientist 2 mock analysis data.csv 1.gz` (215 MB compressed, ~1.5 GB uncompressed)
- **Rows:** 7,625,105 (plus header) — ~7.6 million user accounts
- **Columns:** 33

### Column Inventory

| # | Column | Type | Description | Missing % (200k sample) |
|---|--------|------|-------------|------------------------|
| 1 | USER_ID | int | Unique identifier | 0% |
| 2 | ACCOUNT_CREATE_DATE | datetime | Account creation timestamp | 0% |
| 3 | ACCOUNT_TYPE | categorical | "Public" or "Member" | 0% |
| 4 | USER_CURRENT_AGE | int | Current age in years | 0% |
| 5 | COUNTRY | string | User's country | 0% |
| 6 | PROVINCE | string | User's province/state | 0% (but 97% = "Unknown") |
| 7 | CITY | string | User's city | 0% (but 97% = "Unknown" or "Redacted") |
| 8 | USER_WORLD_REGION | categorical | Geographic macro-region (7 values) | 0% |
| 9 | USER_AREA_NAME | categorical | FamilySearch organizational area (~20 values) | 0% |
| 10 | EARLIEST_LOGIN_DATE | datetime | First login date | **15.6%** |
| 11 | EARLIEST_NAME_CONTRIBUTOR_DATE | datetime | First name contribution | **47.9%** |
| 12 | EARLIEST_SOURCE_CONTRIBUTOR_DATE | datetime | First source added | **91.6%** |
| 13 | EARLIEST_MEMORY_CONTRIBUTOR_DATE | datetime | First memory added | **97.6%** |
| 14 | EARLIEST_GET_INVOLVED_USAGE_DATE | datetime | First "Get Involved" use | **99.4%** |
| 15 | EARLIEST_RECORD_EDIT_DATE | datetime | First record edit | **99.4%** |
| 16 | EARLIEST_TREE_EDIT_DATE | datetime | First tree edit | **46.8%** |
| 17 | DAYS_LOGGING_IN | float | Total distinct days logged in | **10.0%** |
| 18 | SOURCES_ADDED | float | Total sources added | 10.0% |
| 19 | DAYS_ADDING_SOURCES | float | Days on which sources were added | 10.0% |
| 20 | MEMORIES_ADDED | float | Total memories added | 10.0% |
| 21 | DAYS_ADDING_MEMORIES | float | Days on which memories were added | 10.0% |
| 22 | GET_INVOLVED_ITEMS_REVIEWED | float | Total Get Involved items reviewed | 10.0% |
| 23 | DAYS_REVIEWING_GET_INVOLVED_ITEMS | float | Days reviewing Get Involved | 10.0% |
| 24 | RECORD_EDITS | float | Total record edits | 10.0% |
| 25 | DAYS_EDITING_RECORDS | float | Days editing records | 10.0% |
| 26 | TREE_EDITS | float | Total family tree edits | 10.0% |
| 27 | DAYS_EDITING_TREES | float | Days editing trees | 10.0% |
| 28 | DAYS_ADDING_NAMES | float | Days on which names were added | **48.3%** |
| 29 | TOTAL_NAMES_ADDED | float | Total names added to tree | 48.3% |
| 30 | DECEASED_NAMES_ADDED | float | Deceased individuals added | 48.3% |
| 31 | LIVING_NAMES_ADDED | float | Living individuals added | 48.3% |
| 32 | NOVEL_NAMES_ADDED | float | New/novel names added | 48.3% |
| 33 | QUALIFIED_NAMES_ADDED | float | Qualified names added | 48.3% |

---

## 3. Key Data Findings

### 3.1 Demographics

**Account Type:**
- 97% Public, 3% Member
- Members are dramatically more active: 3x login days, 2x tree edits, 2x sources, 37x Get Involved items

**Age Distribution:**
- Range: -1 to 150 (data quality issues at extremes — ~553 users age 100+, some age -1)
- Mean: 35, Median: 30
- Large youth cohort: 12.5% are ages 13-17 (likely church youth programs)
- Peak engagement increases with age: users 56-65 log in ~2x as much as 18-25

**Geography:**
- Latin America (38.7%), North America (27.8%), Europe (22.3%), Asia Pacific (7.1%)
- Top countries: United States (26%), Brazil (21%), Mexico (5%), Philippines (3%), Argentina (3%)
- Province/City mostly "Unknown" (97%) — very limited granularity below country level
- Africa region has highest avg tree edits (41) and sources added (21) despite being smallest group

**Account Creation Date Range:** 2025-01-01 to 2025-12-30 (full year as stated)

### 3.2 Engagement Patterns

**Login Frequency (among users with data):**
| Tier | % of Users | Description |
|------|-----------|-------------|
| 0 logins | 6.5% | Created account, never logged in (or logged in same day as creation only) |
| 1 login | 58.1% | One-and-done — the dominant pattern |
| 2-5 logins | 24.5% | Light returners |
| 6-30 logins | 8.4% | Moderate engagement |
| 31+ logins | 2.5% | Power users |

**Critical finding: ~64% of users log in 0-1 times.** The vast majority are one-and-done.

**Behavioral Segments (rough manual cuts):**
- Never logged in: 15.8%
- Logged in but zero contributions: 36.4%
- Light contributors (1-5 logins, <50 actions): 35.3%
- Heavy contributors (10+ logins, 50+ actions): 2.2%

### 3.3 Activity Type Specialization

**Activity participation rates (of all users):**
- Tree edits: ~53% have at least some tree edits (most common contribution)
- Name additions: ~52% added at least one name
- Source additions: only 8.1%
- Memories: only 2.3%
- Get Involved: only 0.6% (but those who do contribute heavily — avg 3.4 items)
- Record edits: only 0.6%

**Specialization is extreme:**
- 39.2% of users ONLY do tree edits (no other contribution type)
- Only 0.1% ONLY do Get Involved
- Multi-activity users (2+ types): only 8.6%
- Users doing 3+ activity types: 1.4%

### 3.4 Correlations & Relationships

**Strongest correlations:**
- TREE_EDITS ↔ SOURCES_ADDED: 0.83 (very strong — source adders are tree builders)
- TREE_EDITS ↔ TOTAL_NAMES_ADDED: 0.82 (adding names = editing tree)
- SOURCES_ADDED ↔ TOTAL_NAMES_ADDED: 0.53

**Weak/no correlations:**
- GET_INVOLVED_ITEMS_REVIEWED is largely independent of other activities (r < 0.08 with everything)
- RECORD_EDITS weakly correlated with other activities

**Key insight:** There appear to be distinct "activity modes" — tree building (names+edits+sources) vs. Get Involved (indexing/volunteering) vs. record editing — that are largely independent.

### 3.5 Name Columns Deep Dive

- Name columns are only populated for users who added at least 1 name (min TOTAL_NAMES_ADDED = 1 when non-null)
- DECEASED + LIVING ≈ TOTAL (84.7% exact match — some rounding or other category)
- NOVEL + QUALIFIED ≠ TOTAL (only 4.7% match — these are likely overlapping subtypes, not a partition)

### 3.6 Account Age vs Activity

Older accounts (more time to accumulate) predictably show more activity:
| Account Age | Avg Logins | Avg Tree Edits | Avg Names |
|-------------|-----------|---------------|-----------|
| 31-90 days | 1.3 | 15.1 | 7.4 |
| 91-180 days | 2.3 | 14.3 | 7.1 |
| 181-365 days | 4.5 | 19.3 | 8.4 |
| 366+ days | 5.2 | 22.3 | 9.4 |

**Implication:** Account age is a confound. Features should be normalized by account tenure (e.g., edits per day, logins per week) to avoid clustering by how long someone has had an account.

---

## 4. Data Quality Issues & Risks

| Issue | Severity | Detail |
|-------|----------|--------|
| **Massive missing data in activity columns** | HIGH | 10% of rows have ALL activity metrics null (cols 17-27). The name columns (28-33) are 48% null. Need decision: impute zeros vs. exclude. |
| **Province/City almost entirely "Unknown"** | MEDIUM | 97% Unknown — these columns are essentially useless for segmentation |
| **Age outliers** | LOW | Ages -1 and 100+ exist (~0.3%). Need to cap/filter. |
| **Login before account creation** | MEDIUM | 21% of users have earliest_login_date before account_create_date. Likely timezone artifacts or data pipeline issues. Not a blocker but worth noting. |
| **Extreme right skew** | HIGH | All activity metrics are massively right-skewed (mean >> median). Top 1% dominate totals. Log transforms or robust scaling essential. |
| **7.6M rows** | MEDIUM | Full dataset is large. Will need sampling strategy or efficient processing. A 500k-1M sample should be sufficient for clustering. |
| **Confound: account age** | HIGH | Older accounts naturally accumulate more activity. Must normalize by tenure. |
| **Sparse activities** | MEDIUM | Sources (8%), Memories (2%), Get Involved (0.6%), Record Edits (0.6%) are very sparse. May need to combine or use binary flags. |

---

## 5. Preliminary Answers to Assignment Questions

### Workflow (what I'd write)
- **Goal interpretation:** Unsupervised segmentation of new FamilySearch users to identify behavioral archetypes — not predict churn or LTV, but describe "who are these users and what do they do?"
- **First questions:** (1) What does the activity landscape look like? (2) How many users never engage at all? (3) Are there natural clusters in behavior types?
- **Workflow:** EDA → feature engineering (normalize by tenure, create ratios, binary flags) → clustering (K-Means + silhouette analysis, possibly HDBSCAN) → profile & interpret → business recommendations
- **Assumptions:** Null activity = zero activity (user didn't do it), account age confound must be addressed
- **Risks:** Dominant inactive segment may swamp clusters; extreme skew; sparse features
- **Reproducibility:** Jupyter notebooks, requirements.txt, modular code, random seeds

### EDA (covered above in Section 3)

### Modeling (approach I'd recommend)
- **Technique:** K-Means clustering (interpretable, well-understood, works well for this scale) with silhouette score + elbow method for k selection. Possibly compare with HDBSCAN for density-based alternative.
- **Feature engineering priorities:**
  - Tenure-normalized rates (logins/week, edits/week)
  - Activity type flags (binary: did they ever add sources? memories? etc.)
  - Engagement depth (number of distinct activity types)
  - Recency features (days from account creation to first activity)
  - Age buckets, region encoding
- **Expected k:** Likely 4-6 segments based on the manual cuts above
- **Validation:** Silhouette score, cluster stability (bootstrap), between-cluster vs. within-cluster variance

### Insights (preliminary hypotheses)
Based on this initial scan, I'd expect segments like:
1. **Ghost accounts** (~16%): Created but never logged in
2. **One-and-done browsers** (~30%): Single login, no contributions
3. **Casual tree builders** (~35%): 1-5 logins, small family tree activity
4. **Engaged genealogists** (~8%): Regular logins, moderate tree + source work
5. **Power contributors** (~2%): Heavy multi-activity users, disproportionate contribution
6. **Get Involved volunteers** (~0.5%): Focused on indexing/reviewing, different motivation

**Key business insight:** The funnel from account creation → first login → first contribution → sustained engagement has massive drop-off at each stage. The biggest opportunity is converting the 30% one-and-done users into casual contributors.

---

## 6. Technical Approach Recommendations

### For the actual implementation:
1. **Sample:** Use 500k-1M row sample (stratified by region/account type) for modeling
2. **Feature set:** ~15-20 engineered features, not raw columns
3. **Preprocessing:** Log1p transform for skewed counts, StandardScaler, handle nulls as zeros
4. **Primary model:** K-Means with k=4-7, evaluated by silhouette + gap statistic
5. **Secondary model:** HDBSCAN as comparison (handles arbitrary cluster shapes)
6. **Visualization:** t-SNE/UMAP for 2D projection, radar/spider charts for segment profiles
7. **Presentation:** Executive summary with segment personas, key metrics table, recommendations

### Folder Structure
```
familysearch_hw/
├── data/                  # Raw + processed data
├── notebooks/             # Jupyter notebooks (01_eda.ipynb, 02_modeling.ipynb)
├── src/                   # Modular Python code
│   ├── features.py        # Feature engineering
│   ├── clustering.py      # Model training
│   └── visualization.py   # Plotting utilities
├── outputs/               # Charts, reports, exports
├── requirements.txt       # Dependencies
└── README.md              # Project overview
```
