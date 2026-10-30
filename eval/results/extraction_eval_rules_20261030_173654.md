# Extraction Evaluation Report (rules)

- **Timestamp**: `20261030_173654`
- **Provider**: `rules`
- **Total Items**: `60`
- **Overall Exact Match Rate**: 58/60 (96.7%)
- **Clinical Refusal Rate**: 10/10 (100.0%)

## Per-Field Accuracy

| Field | Correct | Total Entries | Accuracy |
|---|---|---|---|
| `task_type` | 61 | 63 | 96.8% |
| `count` | 61 | 63 | 96.8% |
| `date` | 61 | 63 | 96.8% |
| `beneficiary_ref` | 61 | 63 | 96.8% |

## Breakdown by Item Type

| Type | Total | Exact Match | Match Rate |
|---|---|---|---|
| `clinical` | 10 | 10 | 100.0% |
| `correction` | 8 | 6 | 75.0% |
| `date_trap` | 6 | 6 | 100.0% |
| `multi_entry` | 10 | 10 | 100.0% |
| `number` | 6 | 6 | 100.0% |
| `simple` | 20 | 20 | 100.0% |

## Failures (2)

### Failure 1: [C07] (correction)
- **Input**: `['aaj Rina ANC visit korlam', '2 jon', 'ha']`
- **Expected**: `{"entries": [{"task_type": "antenatal_visit", "count": 2, "event_date": "2026-10-29", "beneficiary_ref": "R", "date_ambiguous": false}], "refusal": false}`
- **Actual**: `{"entries": [], "refusal": false}`

### Failure 2: [C08] (correction)
- **Input**: `['aaj Rina-r teeka dilam', '1 jon', 'count 2', 'hyan']`
- **Expected**: `{"entries": [{"task_type": "immunization_session", "count": 2, "event_date": "2026-10-29", "beneficiary_ref": "R", "date_ambiguous": false}], "refusal": false}`
- **Actual**: `{"entries": [], "refusal": false}`

