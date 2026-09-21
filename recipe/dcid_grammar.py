"""Parse and format undata DCIDs.

Grammar: undata/<agency>/<CODE>[.<DIM>--<VALUE>[__<DIM2>--<VALUE2>]*]

The dimension suffix is what makes automatic key discovery possible: parsing
it into a structured dict lets the key-matcher compute shared dimensions
across indicators from different agencies without any hand-written mapping
per indicator pair.
"""

from __future__ import annotations

from dataclasses import dataclass

_NOT_APPLICABLE = "_Z"


@dataclass(frozen=True)
class ParsedDcid:
    """Structured decomposition of a Data Commons variable DCID."""

    raw: str
    agency: str | None
    code: str
    dimensions: dict[str, str]
    is_undata: bool


def parse_dcid(dcid: str) -> ParsedDcid:
    """Parse a DCID into agency, base code, and dimension dict.

    Non-undata DCIDs (e.g. base Data Commons variables like `Count_Person`)
    have no agency and no dimensions — they don't follow this grammar, which
    is why they can't participate in automatic key discovery.
    """
    # Lowercase `worldbank/` is a direct World Bank API pull. Note that the
    # camelCase `worldBank/` prefix is something else entirely -- a Data Commons
    # dcid for a World Bank dataset it republishes -- and deliberately falls
    # through to the generic external branch below. The two are different pipes
    # and are never distinguished by sniffing the string; indicators declare
    # which one they use with an explicit `source:` field.
    if dcid.startswith("worldbank/"):
        return ParsedDcid(
            raw=dcid,
            agency="worldbank",
            code=dcid[len("worldbank/") :],
            dimensions={},
            is_undata=False,
        )

    if not dcid.startswith("undata/"):
        return ParsedDcid(
            raw=dcid, agency=None, code=dcid, dimensions={}, is_undata=False
        )

    rest = dcid[len("undata/") :]
    parts = rest.split("/", 1)
    if len(parts) != 2:
        return ParsedDcid(
            raw=dcid, agency=None, code=rest, dimensions={}, is_undata=False
        )

    agency, code_and_dims = parts
    code, _, dim_suffix = code_and_dims.partition(".")

    dimensions: dict[str, str] = {}
    if dim_suffix:
        for chunk in dim_suffix.split("__"):
            dim_name, sep, dim_value = chunk.partition("--")
            if not sep:
                continue
            if dim_value == _NOT_APPLICABLE:
                continue
            dimensions[dim_name] = dim_value

    return ParsedDcid(
        raw=dcid, agency=agency, code=code, dimensions=dimensions, is_undata=True
    )


def format_dcid(
    agency: str, code: str, dimensions: dict[str, str] | None = None
) -> str:
    """Reconstruct a canonical DCID, with dimensions sorted alphabetically by name.

    Sorting makes two DCIDs with the same dimensions but written in different
    orders compare equal after parsing and reformatting.
    """
    if not dimensions:
        return f"undata/{agency}/{code}"
    suffix = "__".join(f"{k}--{v}" for k, v in sorted(dimensions.items()))
    return f"undata/{agency}/{code}.{suffix}"
