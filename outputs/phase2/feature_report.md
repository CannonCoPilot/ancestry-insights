# Phase 2: Feature Engineering Report

**Generated**: 2026-03-26T03:13:44.965539
**Table**: users_features (7,625,105 rows, 79 columns)

---

## QC Log

| Step | Metric | Value | Note |
|------|--------|-------|------|
| 2.7 | unpivoted_milestone_rows | 15322688 |  |
| 2.7 | users_with_sequences | 6843719 |  |
| 2.7 | sequences_populated | 6843719 |  |
| 2.7 | sequences_empty | 781386 | Users with no milestone dates |
| 2.7 | distinct_sequences | 1184 |  |
| 2.7 | seq:L>N>T | 2846091 | 37.3% |
| 2.7 | seq:L | 2754658 | 36.1% |
| 2.7 | seq:N>T | 364478 | 4.8% |
| 2.7 | seq:L>N>S>T | 291954 | 3.8% |
| 2.7 | seq:L>N>T>S | 114986 | 1.5% |
| 2.7 | seq:L>M>N>T | 51924 | 0.7% |
| 2.7 | seq:L>T | 49725 | 0.7% |
| 2.7 | seq:L>S | 35503 | 0.5% |
| 2.7 | seq:L>N>T>M | 33281 | 0.4% |
| 2.7 | seq:N>S>T | 29043 | 0.4% |
| 2.7 | seq:N>T>L | 28658 | 0.4% |
| 2.7 | seq:L>M>N>S>T | 20761 | 0.3% |
| 2.7 | seq:L>N>T>M>S | 15451 | 0.2% |
| 2.7 | seq:L>S>T | 14212 | 0.2% |
| 2.7 | seq:L>N>S>T>M | 12821 | 0.2% |
| 2.7 | seq:L>N>T>S>M | 8378 | 0.1% |
| 2.7 | seq:L>T>N | 8042 | 0.1% |
| 2.7 | seq:L>N>T>G | 7835 | 0.1% |
| 2.7 | seq:T | 7234 | 0.1% |
| 2.7 | seq:G>L>N>T | 7194 | 0.1% |
| 2.14 | persistence_c_median | 0.142857 |  |
| 2.14 | persistence_c_p33 | 0.070273 |  |
| 2.14 | persistence_c_p67 | 0.155748 |  |
| 2.14 | persist_median:0 | 3423978 | 50.0% |
| 2.14 | persist_median:1 | 3429608 | 50.0% |
| 2.14 | persist_tertile:0 | 2279970 | 33.3% |
| 2.14 | persist_tertile:1 | 2287736 | 33.4% |
| 2.14 | persist_tertile:2 | 2285880 | 33.4% |
| 2.13 | corr_A_B | 0.0476 |  |
| 2.13 | corr_A_C | 0.6925 |  |
| 2.13 | corr_B_C | 0.1602 |  |
| 2.15 | final_columns | 79 |  |
| 2.15 | final_rows | 7625105 |  |
| 2.15 | rows_preserved | True |  |
| 2.15 | avg_days_to_first_login | 0.9742 |  |
| 2.15 | med_days_to_first_login | 0.0 |  |
| 2.15 | avg_activation_speed | 0.8897 |  |
| 2.15 | avg_logins_pw | 0.1127 |  |
| 2.15 | avg_tree_edits_pw | 0.5862 |  |
| 2.15 | avg_names_pw | 0.1523 |  |
| 2.15 | avg_breadth | 2.1663 |  |
| 2.15 | avg_persist_a | 0.1127 |  |
| 2.15 | avg_persist_b | 0.0167 |  |
| 2.15 | avg_persist_c | 0.1398 |  |
| 2.15 | min_persist_c | 0.0 |  |
| 2.15 | max_persist_c | 0.9029 |  |
| 2.15 | funnel:0 | 2500 | 0.0% |
| 2.15 | funnel:1 | 2790534 | 40.7% |
| 2.15 | funnel:2 | 3394679 | 49.5% |
| 2.15 | funnel:3 | 582740 | 8.5% |
| 2.15 | funnel:4 | 83133 | 1.2% |
| 2.15 | cluster:High-LDS-International | 3145563 | 41.3% |
| 2.15 | cluster:Mod-Eng-US-Other | 1968626 | 25.8% |
| 2.15 | cluster:Mod-Eng-Low-LDS | 1466764 | 19.2% |
| 2.15 | cluster:Micro-Other | 729222 | 9.6% |
| 2.15 | cluster:Low-Eng-Developing | 247722 | 3.2% |
| 2.15 | cluster:Low-Eng-High-Dev | 40541 | 0.5% |
| 2.15 | cluster:High-LDS-US-Utah | 26667 | 0.3% |