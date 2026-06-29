from src.pipeline_diagram import _normalize_mermaid


def test_normalize_mermaid_removes_full_line_comments():
    raw = """```mermaid
flowchart LR
%% Joins from main pivot and previous join
A --> B
```"""

    normalized = _normalize_mermaid(raw)

    assert normalized == "flowchart TB\nA --> B"


def test_normalize_mermaid_removes_inline_comments():
    raw = """flowchart LR
A --> B %% pivot join
B --> C
"""

    normalized = _normalize_mermaid(raw)

    assert normalized == "flowchart TB\nA --> B\nB --> C"


def test_normalize_mermaid_splits_combined_class_shorthand():
    raw = """flowchart TB
A["Nodo A"]:::raw.pivot
B["Nodo B"]:::process.highlight
A --> B
"""

    normalized = _normalize_mermaid(raw)

    assert normalized == 'flowchart TB\nA["Nodo A"]:::raw:::pivot\nB["Nodo B"]:::process:::highlight\nA --> B'
