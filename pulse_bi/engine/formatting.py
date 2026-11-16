"""Number formatting shared by the dashboard, emails and chat replies."""


def inr(value, decimals=0):
    """Indian digit grouping: 1234567.8 -> 12,34,568 (or 12,34,567.80)."""
    if value is None:
        return "n/a"
    number = round(float(value), decimals)
    sign = "-" if number < 0 else ""
    whole, _, fraction = f"{abs(number):.{decimals}f}".partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups) + "," + tail
    return sign + whole + ("." + fraction if fraction else "")
