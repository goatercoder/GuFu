"""Row-label -> canonical field mapping for old 10-K tables."""

from __future__ import annotations

import re

PER_SHARE_RE = re.compile(r"per\s+(common\s+|diluted\s+|basic\s+)?share|per\s+adr|per\s+unit", re.I)

# (field, regex, exclude_regex). Evaluated in order; first match wins for a label.
# Labels are lower-cased and whitespace-normalised before matching.
_R = [
    # ---- shares
    ("shares_diluted", r"(weighted[-\s]average|average)\s+(number\s+of\s+)?(common\s+)?(shares|units)[^\n]*(diluted|assuming\s+dilution)|diluted\s+(weighted[-\s]average\s+)?shares|shares\s+used\s+in\s+(computing\s+)?diluted", None),
    ("shares_basic", r"(weighted[-\s]average|average)\s+(number\s+of\s+)?(common\s+)?shares|shares\s+used\s+in\s+(computing\s+)?basic", r"diluted"),
    ("shares_outstanding", r"(common\s+)?shares\s+outstanding(\s+at\s+(year|period)[-\s]end)?$|shares\s+outstanding\s+at\s+end", r"weighted|average"),
    # ---- per-share (checked first so "net income per share" never becomes net income)
    ("dps", r"(cash\s+)?dividends?\s+(declared|paid)?\s*(per\s+(common\s+)?share)|dividends?\s+per\s+(common\s+)?share|per\s+share\s+dividends?", None),
    ("eps_diluted", r"(diluted|assuming\s+dilution|fully\s+diluted)", r"loss\s+from\s+discontinued|discontinued|extraordinary|cumulative\s+effect|before|shares|weighted|average|number"),
    ("eps_basic", r"(basic|primary)\b", r"discontinued|extraordinary|cumulative\s+effect|before|shares|weighted|average|number"),
    ("eps_diluted", r"(net\s+)?(income|earnings)\s*(\(loss\))?\s+per\s+(common\s+)?share", r"discontinued|extraordinary|before|continuing"),
    ("bvps", r"book\s+value\s+per\s+(common\s+)?share", None),
    # ---- income statement
    ("revenue", r"^(total\s+)?(net\s+)?(sales|revenues?)(\s+and\s+other\s+(operating\s+)?(income|revenues?))?$|^(total\s+)?(net\s+)?operating\s+revenues?$|^net\s+sales\s+and\s+(operating\s+)?revenues?$|^(total\s+)?revenues?,?\s+net$|^sales\s+and\s+revenues?$|^total\s+net\s+(sales|revenues?)$|^revenues?\s+from\s+(product\s+)?sales|^net\s+revenues?\s+from|^total\s+revenues?\s+and\s+other\s+income", r"cost|\bper\b|percent|growth|%|interest\s+income$"),
    ("revenue", r"^(net\s+)?(sales|revenues?)\s*\(.*\)$|^(net\s+)?(sales|revenues?)\s+\(note", None),
    ("cost_of_revenue", r"^(total\s+)?cost\s+of\s+((goods|products?)\s+(sold|and\s+services)|sales|revenues?|services|merchandise)|^cost\s+of\s+sales", r"gross|percent|%"),
    ("gross_profit", r"^gross\s+(profit|margin|income)$|^gross\s+(profit|margin)\s+on\s+sales", r"percent|%|per"),
    ("rnd", r"research(,?\s+development)?(\s+and\s+(development|engineering))?", r"percent|%"),
    ("sga", r"selling,?\s+(general\s+)?(and|&)\s+administrative|^s,?\s?g\s?&\s?a|^selling\s+and\s+administrative|^general\s+and\s+administrative", r"percent|%"),
    ("dna", r"^depreciation(,|\s+and)?\s*(depletion)?(,|\s+and)?\s*(amortization)?$|^depreciation\s+and\s+amortization|^amortization\s+and\s+depreciation", None),
    ("operating_income", r"^(total\s+)?(income|earnings|profit)\s*(\(loss\))?\s+from\s+operations$|^operating\s+(income|earnings|profit)\s*(\(loss\))?$|^operating\s+(income|profit)\s*\(loss\)|^(income|earnings)\s*(\(loss\))?\s+from\s+continuing\s+operations\s+before\s+interest", r"\bper\b|percent|%|margin|discontinued"),
    ("interest_expense", r"^interest\s+expense(,?\s+net)?$|^interest\s+(and\s+debt\s+)?expense|^interest\s+expense,?\s+net\s+of", r"income|percent|%"),
    ("pretax_income", r"(income|earnings)\s*(\(loss\))?\s+(from\s+continuing\s+operations\s+)?before\s+(provision\s+for\s+|income\s+)?(income\s+)?tax", r"\bper\b|discontinued\s+operations$|minority|cumulative|extraordinary"),
    ("tax_expense", r"^(provision\s+for|provision\s+\(benefit\)\s+for)?\s*income\s+tax(es)?(\s+(expense|provision|\(benefit\)|benefit))?$|^income\s+tax(es)?\s+(expense|provision)|^taxes\s+on\s+income|^provision\s+for\s+(income\s+)?taxes", r"before|deferred|per|refund|payable|receivable|net\s+of|paid"),
    ("net_income", r"^net\s+(income|earnings|profit)\s*(\(loss\))?$|^net\s+(income|earnings)\s*(\(loss\))?\s+(attributable\s+to|available\s+to|applicable\s+to)\s+(common|.*shareholders|.*stockholders|.*company)|^net\s+(income|earnings)\s*\(loss\)\s*$|^net\s+(loss|earnings)$", r"\bper\b|share|discontinued\s+operations$|before|minority\s+interest$|percent|%|margin|non-?controlling\s+interest$|extraordinary"),
    ("net_income_cont", r"^(net\s+)?(income|earnings)\s*(\(loss\))?\s+from\s+continuing\s+operations$", r"\bper\b|before|share"),
    # ---- balance sheet
    ("total_assets", r"^total\s+assets$", None),
    ("current_assets", r"^total\s+current\s+assets$", None),
    ("current_liabilities", r"^total\s+current\s+liabilities$", None),
    ("cash", r"^cash(\s+and\s+(cash\s+)?equivalents)?$|^cash\s+and\s+(cash\s+equivalents|short[-\s]term\s+investments)|^cash\s+and\s+due\s+from\s+banks", r"flow|provided|used|net\s+(increase|decrease|change)|beginning|end\s+of|restricted|paid"),
    ("short_term_investments", r"^(short[-\s]term|marketable)\s+(investments|securities)$|^short[-\s]term\s+marketable", None),
    ("receivables", r"^(accounts|trade|net)\s+(and\s+notes\s+)?receivables?(,?\s+net)?|^receivables?(,?\s+net)?$", r"allowance|long"),
    ("inventory", r"^(merchandise\s+)?inventor(y|ies)(,?\s+net)?$|^inventor(y|ies)\s+at\s+", None),
    ("ppe_net", r"^(net\s+)?property,?\s+plant(,?\s+and|\s+&)?\s+equipment(,?\s+net)?$|^property\s+and\s+equipment(,?\s+net)?$|^net\s+property", r"additions|purchases|gross|accumulated"),
    ("goodwill", r"^goodwill(,?\s+net)?$|^goodwill\s+and\s+(other\s+)?intangible", None),
    ("intangibles", r"^(other\s+)?intangible\s+assets(,?\s+net)?$|^intangibles(,?\s+net)?$", r"goodwill"),
    ("long_term_debt", r"^long[-\s]term\s+(debt|borrowings|obligations|notes)(,?\s+(net\s+of|less|excluding)\s+current\s+(portion|maturities))?(,?\s+net)?$|^long[-\s]term\s+debt,?\s+(net\s+of|less|excluding)\s+current|^long[-\s]term\s+debt\s+and\s+(capital\s+)?lease|^long[-\s]term\s+debt$|^total\s+long[-\s]term\s+debt", r"current\s+portion\s+of|current\s+maturities\s+of\s+long|percent|%|ratio|to\s+(total\s+)?capital|including\s+current"),
    ("total_debt_reported", r"^total\s+(debt|borrowings)$|^total\s+debt\s+\(|^debt$|^total\s+long[-\s]term\s+debt\s+including\s+current", r"ratio|percent|%|to\s+"),
    ("total_liabilities", r"^total\s+liabilities$", None),
    ("retained_earnings", r"^retained\s+earnings(\s*\(accumulated\s+deficit\))?$|^reinvested\s+earnings|^earnings\s+(retained|reinvested)", None),
    ("liabilities_and_equity", r"^total\s+liabilities\s+and\s+(stock|share)(holders|owners)'?\s*equity|^total\s+liabilities,?\s+.*equity$", None),
    ("equity", r"^(total\s+)?(common\s+)?(stock|share)(holders|owners)'?\s*(equity|investment)$|^(total\s+)?(stock|share)(holders|owners)'?\s*equity\s*\(deficit\)|^total\s+equity$|^(total\s+)?(stock|share)(holders|owners)'?\s+equity\s+attributable", r"per\s+share|return|liabilities|ratio|percent|%|to\s+"),
    ("working_capital", r"^working\s+capital$", r"ratio"),
    # ---- cash flow
    ("ocf", r"^(net\s+)?cash\s+(provided|generated)\s+(by|from)\s+(\(used\s+in\)\s+)?operat|^net\s+cash\s+(flows?\s+)?(from|provided\s+by)\s+operat|^cash\s+flows?\s+from\s+operat|^(net\s+)?cash\s+from\s+operations|^operating\s+cash\s+flow|^cash\s+flow\s+from\s+operations|^net\s+cash\s+\(used\s+in\)\s+provided\s+by\s+operat", r"\bper\b|investing|financing"),
    ("capex", r"^(capital\s+expenditures?|capital\s+spending|additions\s+to\s+property|purchases?\s+of\s+property|expenditures\s+for\s+property|payments\s+for\s+property|property\s+additions|investment\s+in\s+property|acquisition\s+of\s+property)", r"\bper\b|percent|%|business|acquisitions?\s+of\s+business"),
    ("dividends_paid", r"^(cash\s+)?dividends\s+(paid|declared)?(\s+on\s+common\s+stock)?$|^(cash\s+)?dividends\s+paid|^payments?\s+of\s+(cash\s+)?dividends|^dividends\s+to\s+(share|stock)holders", r"per\s+share|preferred|minority"),
    ("buybacks", r"(purchases?|repurchases?|acquisition|retirement)\s+of\s+(common\s+|treasury\s+)?(stock|shares)|^treasury\s+stock\s+(purchases?|acquired)|^(common\s+)?stock\s+repurchase", r"per\s+share|issued|proceeds"),
]

_COMPILED = [(f, re.compile(p, re.I), re.compile(x, re.I) if x else None) for f, p, x in _R]

# Fields whose values are per share (scale never applies)
PER_SHARE_FIELDS = {"dps", "eps_diluted", "eps_basic", "bvps"}
# Fields that must be treated as cash *outflows* stored positive in our schema
OUTFLOW_FIELDS = {"capex", "dividends_paid", "buybacks", "cost_of_revenue", "rnd", "sga", "interest_expense", "tax_expense", "dna"}

SUMMARY_FIELDS = {"revenue", "operating_income", "net_income", "net_income_cont", "eps_diluted", "eps_basic", "dps", "total_assets",
                  "long_term_debt", "total_debt_reported", "equity", "ocf", "capex", "working_capital", "shares_diluted",
                  "shares_basic", "shares_outstanding", "cash", "current_assets", "current_liabilities", "gross_profit",
                  "rnd", "dna", "bvps", "pretax_income", "tax_expense", "interest_expense", "cost_of_revenue", "sga",
                  "dividends_paid", "buybacks", "ppe_net", "total_liabilities", "retained_earnings"}
INCOME_FIELDS = {"revenue", "cost_of_revenue", "gross_profit", "rnd", "sga", "dna", "operating_income", "interest_expense",
                 "pretax_income", "tax_expense", "net_income", "net_income_cont", "eps_diluted", "eps_basic",
                 "shares_diluted", "shares_basic", "dps"}
BALANCE_FIELDS = {"cash", "short_term_investments", "receivables", "inventory", "current_assets", "ppe_net", "goodwill",
                  "intangibles", "total_assets", "current_liabilities", "long_term_debt", "total_liabilities",
                  "retained_earnings", "equity", "liabilities_and_equity", "working_capital", "shares_outstanding",
                  "total_debt_reported"}
CASHFLOW_FIELDS = {"dna", "ocf", "capex", "dividends_paid", "buybacks", "net_income"}


def normalise_label(label: str) -> str:
    s = label.lower().replace("’", "'").replace("–", "-").replace("—", "-")
    s = re.sub(r"\([^)]*\)", lambda m: m.group(0) if "loss" in m.group(0) else " ", s)  # drop footnote/parenthetical notes except (loss)
    s = re.sub(r"[^a-z0-9'&,\-\s()]", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" :.-")
    return s


def map_label(label: str, allowed: set[str] | None = None) -> str | None:
    s = normalise_label(label)
    if not s:
        return None
    per_share = bool(PER_SHARE_RE.search(s))
    for field, rx, ex in _COMPILED:
        if allowed is not None and field not in allowed:
            continue
        if field not in PER_SHARE_FIELDS and per_share:
            continue
        if field in PER_SHARE_FIELDS and not per_share and field not in ("eps_diluted", "eps_basic"):
            continue
        if rx.search(s) and not (ex and ex.search(s)):
            return field
    return None
