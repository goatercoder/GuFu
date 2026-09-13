"""Canonical financial fields and the ordered us-gaap / dei tag fallback lists that feed them.

The first tag (per period) that has a value wins. Lists are ordered from the most common modern tag
to older / rarer variants so that companies that switched taxonomies (ASC 606 in 2018, the 2024
InterestExpenseNonoperating rename, ...) still produce a continuous series.
"""

from __future__ import annotations

from dataclasses import dataclass

DURATION = "duration"
INSTANT = "instant"


@dataclass(frozen=True)
class FieldSpec:
    key: str
    label: str
    kind: str  # duration | instant
    unit: str = "USD"  # USD | USD/shares | shares
    tags: tuple[str, ...] = ()
    # Optional component tags summed together when none of `tags` is present (e.g. short-term debt).
    components: tuple[str, ...] = ()
    group: str = "income"  # income | cashflow | balance | pershare
    # When True the quarterly value is NOT derived by subtracting cumulative periods (e.g. share counts).
    no_subtract: bool = False


def _f(key, label, kind, tags, unit="USD", components=(), group="income", no_subtract=False):
    return FieldSpec(key, label, kind, unit, tuple(tags), tuple(components), group, no_subtract)


FIELD_SPECS: dict[str, FieldSpec] = {
    s.key: s
    for s in [
        # ---------------- income statement (duration) ----------------
        _f("revenue", "Revenue", DURATION, [
            "RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet",
            "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueGoodsNet",
            "SalesRevenueServicesNet", "RevenuesNetOfInterestExpense", "TotalRevenuesAndOtherIncome",
            "RegulatedAndUnregulatedOperatingRevenue", "OperatingLeasesIncomeStatementLeaseRevenue",
            "InterestAndDividendIncomeOperating", "RevenuesExcludingInterestAndDividends",
            "HealthCareOrganizationRevenue", "OilAndGasRevenue", "ElectricUtilityRevenue",
        ]),
        _f("cost_of_revenue", "Cost of Revenue", DURATION, [
            "CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold", "CostOfServices",
            "CostOfGoodsAndServicesSoldExcludingDepreciationDepletionAndAmortization",
            "CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization",
        ]),
        _f("gross_profit", "Gross Profit", DURATION, ["GrossProfit"]),
        _f("rnd", "R&D Expense", DURATION, [
            "ResearchAndDevelopmentExpense", "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost",
        ]),
        _f("sga", "SG&A Expense", DURATION, ["SellingGeneralAndAdministrativeExpense"]),
        _f("operating_income", "Operating Income", DURATION, ["OperatingIncomeLoss"]),
        _f("interest_expense", "Interest Expense", DURATION, [
            "InterestExpenseNonoperating", "InterestExpense", "InterestExpenseDebt", "InterestAndDebtExpense",
            "InterestExpenseNet", "InterestPaidNet",
        ]),
        _f("pretax_income", "Pretax Income", DURATION, [
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic",
        ]),
        _f("tax_expense", "Income Tax Expense", DURATION, ["IncomeTaxExpenseBenefit"]),
        _f("net_income", "Net Income", DURATION, [
            "NetIncomeLoss", "NetIncomeLossAvailableToCommonStockholdersBasic", "ProfitLoss",
            "IncomeLossFromContinuingOperations", "NetIncomeLossAttributableToParentDiluted",
        ]),
        _f("dna", "Depreciation & Amortization", DURATION, [
            "DepreciationDepletionAndAmortization", "DepreciationAndAmortization",
            "DepreciationAmortizationAndAccretionNet", "DepreciationAmortizationAndOther", "Depreciation",
            "DepreciationDepletionAndAmortizationPropertyPlantAndEquipment",
        ], group="cashflow"),
        _f("eps_diluted", "EPS (Diluted)", DURATION, [
            "EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted", "EarningsPerShareBasic",
        ], unit="USD/shares", group="pershare"),
        _f("shares_diluted", "Diluted Shares (Weighted)", DURATION, [
            "WeightedAverageNumberOfDilutedSharesOutstanding",
            "WeightedAverageNumberOfShareOutstandingBasicAndDiluted",
            "WeightedAverageNumberOfSharesOutstandingBasic",
        ], unit="shares", group="pershare", no_subtract=True),
        _f("dps", "Dividends per Share", DURATION, [
            "CommonStockDividendsPerShareDeclared", "CommonStockDividendsPerShareCashPaid",
        ], unit="USD/shares", group="pershare"),
        # ---------------- cash flow (duration, YTD in 10-Qs) ----------------
        _f("ocf", "Operating Cash Flow", DURATION, [
            "NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
        ], group="cashflow"),
        _f("capex", "Capital Expenditure", DURATION, [
            "PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets",
            "PaymentsForCapitalImprovements", "PaymentsToAcquireOtherPropertyPlantAndEquipment",
            "PaymentsToAcquireOilAndGasPropertyAndEquipment",
        ], group="cashflow"),
        _f("dividends_paid", "Dividends Paid", DURATION, [
            "PaymentsOfDividendsCommonStock", "PaymentsOfDividends", "PaymentsOfOrdinaryDividends",
            "DividendsCommonStockCash", "DividendsCommonStock", "PaymentsOfDividendsMinorityInterest",
        ], group="cashflow"),
        _f("buybacks", "Share Buybacks", DURATION, [
            "PaymentsForRepurchaseOfCommonStock", "PaymentsForRepurchaseOfEquity",
            "StockRepurchasedDuringPeriodValue", "StockRepurchasedAndRetiredDuringPeriodValue",
        ], group="cashflow"),
        # ---------------- balance sheet (instant) ----------------
        _f("total_assets", "Total Assets", INSTANT, ["Assets"], group="balance"),
        _f("current_assets", "Current Assets", INSTANT, ["AssetsCurrent"], group="balance"),
        _f("current_liabilities", "Current Liabilities", INSTANT, ["LiabilitiesCurrent"], group="balance"),
        _f("total_liabilities", "Total Liabilities", INSTANT, ["Liabilities"], group="balance"),
        _f("liabilities_and_equity", "Liabilities & Equity", INSTANT, ["LiabilitiesAndStockholdersEquity"], group="balance"),
        _f("equity", "Shareholders' Equity", INSTANT, [
            "StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        ], group="balance"),
        _f("equity_incl_nci", "Total Equity (incl. NCI)", INSTANT, [
            "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", "StockholdersEquity",
        ], group="balance"),
        _f("cash", "Cash & Equivalents", INSTANT, [
            "CashAndCashEquivalentsAtCarryingValue",
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents", "Cash", "CashAndDueFromBanks",
            "CashCashEquivalentsAndShortTermInvestments",
        ], group="balance"),
        _f("short_term_investments", "Short-term Investments", INSTANT, [
            "ShortTermInvestments", "MarketableSecuritiesCurrent", "AvailableForSaleSecuritiesDebtSecuritiesCurrent",
            "AvailableForSaleSecuritiesCurrent",
        ], group="balance"),
        _f("receivables", "Receivables", INSTANT, ["AccountsReceivableNetCurrent", "ReceivablesNetCurrent"], group="balance"),
        _f("inventory", "Inventory", INSTANT, ["InventoryNet", "InventoryFinishedGoodsNetOfReserves"], group="balance"),
        _f("ppe_net", "PP&E (Net)", INSTANT, ["PropertyPlantAndEquipmentNet"], group="balance"),
        _f("goodwill", "Goodwill", INSTANT, ["Goodwill"], group="balance"),
        _f("intangibles", "Intangibles (ex Goodwill)", INSTANT, ["IntangibleAssetsNetExcludingGoodwill"], group="balance"),
        _f("goodwill_intangibles", "Goodwill & Intangibles", INSTANT, ["IntangibleAssetsNetIncludingGoodwill"], group="balance"),
        _f("long_term_debt", "Long-term Debt", INSTANT, [
            "LongTermDebtNoncurrent", "LongTermDebtAndCapitalLeaseObligations", "LongTermDebt",
            "LongTermNotesPayable", "OtherLongTermDebtNoncurrent", "SeniorLongTermNotes", "ConvertibleLongTermNotesPayable",
        ], group="balance"),
        _f("short_term_debt", "Short-term Debt", INSTANT, ["DebtCurrent"], components=[
            "LongTermDebtCurrent", "ShortTermBorrowings", "CommercialPaper", "NotesPayableCurrent",
            "LongTermDebtAndCapitalLeaseObligationsCurrent", "OtherShortTermBorrowings",
        ], group="balance"),
        _f("total_debt_reported", "Total Debt (reported)", INSTANT, [
            "DebtLongtermAndShorttermCombinedAmount", "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities",
            "DebtAndCapitalLeaseObligations",
        ], group="balance"),
        _f("retained_earnings", "Retained Earnings", INSTANT, ["RetainedEarningsAccumulatedDeficit"], group="balance"),
        _f("shares_outstanding", "Shares Outstanding", INSTANT, [
            "dei:EntityCommonStockSharesOutstanding", "CommonStockSharesOutstanding",
        ], unit="shares", group="pershare"),
    ]
}

# Derived fields (computed in normalize.py) with labels, for charting and API metadata.
DERIVED_FIELDS: dict[str, tuple[str, str, str]] = {
    # key: (label, kind, group)
    "gross_profit": ("Gross Profit", DURATION, "income"),
    "operating_income": ("Operating Income", DURATION, "income"),
    "ebitda": ("EBITDA", DURATION, "income"),
    "fcf": ("Free Cash Flow", DURATION, "cashflow"),
    "total_liabilities": ("Total Liabilities", INSTANT, "balance"),
    "total_debt": ("Total Debt", INSTANT, "balance"),
    "net_debt": ("Net Debt", INSTANT, "balance"),
    "working_capital": ("Working Capital", INSTANT, "balance"),
    "goodwill_intangibles": ("Goodwill & Intangibles", INSTANT, "balance"),
    "bvps": ("Book Value per Share", INSTANT, "pershare"),
    "dps_derived": ("Dividends per Share (derived)", DURATION, "pershare"),
    "fcf_per_share": ("FCF per Share", DURATION, "pershare"),
}

# Fields exposed in the financials chart, in display order.
CHART_FIELDS: list[str] = [
    "revenue", "gross_profit", "operating_income", "ebitda", "net_income", "eps_diluted",
    "ocf", "capex", "fcf", "fcf_per_share", "dividends_paid", "dps", "buybacks", "rnd", "sga",
    "total_assets", "total_liabilities", "equity", "cash", "total_debt", "net_debt",
    "shares_diluted", "shares_outstanding", "bvps", "retained_earnings",
]

ACCEPTED_FORMS = {"10-K", "10-K/A", "10-KT", "10-KT/A", "10-Q", "10-Q/A", "10-QT", "10-QT/A"}


def field_label(key: str) -> str:
    if key in FIELD_SPECS:
        return FIELD_SPECS[key].label
    if key in DERIVED_FIELDS:
        return DERIVED_FIELDS[key][0]
    return key


def field_kind(key: str) -> str:
    if key in FIELD_SPECS:
        return FIELD_SPECS[key].kind
    if key in DERIVED_FIELDS:
        return DERIVED_FIELDS[key][1]
    return DURATION


def field_unit(key: str) -> str:
    if key in FIELD_SPECS:
        return FIELD_SPECS[key].unit
    if key in ("bvps", "dps_derived", "fcf_per_share"):
        return "USD/shares"
    return "USD"
