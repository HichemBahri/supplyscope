# Recommender ablation — criterion influence

160 (category × preset × removed-criterion) cases over 8 categories and 3 presets.

| removed criterion | cases | winner changes | top-3 overlap | Spearman ρ |
|---|---|---|---|---|
| price | 24 | 45.8% | 0.944 | 0.4 |
| lead_time | 24 | 29.2% | 1.0 | 0.713 |
| reliability | 24 | 25.0% | 0.944 | 0.692 |
| quality | 24 | 12.5% | 1.0 | 0.883 |
| ml_risk | 24 | 12.5% | 0.917 | 0.833 |
| terms | 16 | 6.2% | 1.0 | 0.981 |
| technical | 24 | 4.2% | 0.972 | 0.929 |

## ML-risk criterion

Removing the classifier changes the recommended supplier in **12.5%** of cases (3/24); mean rank correlation with the full model 0.833.

- steel/balanced: SUP-IST→SUP-TAC
- electrical/cost_focused: SUP-SEL→SUP-CNE
- valves/cost_focused: SUP-MTL→SUP-CNV
