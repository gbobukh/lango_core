# SafeEvaluator Reference
This document lists the functions, operators, and syntax rules available within the `SafeEvaluator` context (used in Service Builder Actions, Scenarios, and Argument Mapping).

## Syntax Rules
1.  **Strict Python Syntax**: All expressions must be valid Python code.
2.  **Variable Names**: Must be valid Python identifiers.
    *   ✅ `publisher_name`
    *   ✅ `my_var_1`
    *   ❌ `publisher name` (Space not allowed)
    *   ❌ `1_var` (Cannot start with number)

## Allowed Functions
The following functions can be used in your expressions (e.g., `len(my_list)`, `int("123")`):

### Built-in Python Functions
*   `len(obj)`: Return the length of an object (list, string, etc.).
*   `int(x)`: Convert x to an integer. Essential for APIs requiring numbers when DB has strings.
*   `str(x)`: Convert x to a string.
*   `float(x)`: Convert x to a floating point number.
*   `bool(x)`: Convert x to a boolean (True/False).
*   `list(x)`: Convert x to a list.
*   `dict(x)`: Convert x to a dictionary.
*   `abs(x)`: Return the absolute value of x.
*   `round(number, ndigits)`: Round a number.
*   `sum(iterable)`: Sum items in an iterable.
*   `max(iterable)`: Return the largest item.
*   `min(iterable)`: Return the smallest item.

### Custom Helper Functions
*   `find(list, key, value)`: Finds the first dictionary in a `list` where `dict[key] == value`.
    *   *Example*: `find(my_items, 'id', 105)`
*   `get_partner_tracker_identifiers(partner, auth_context)`: Retrieves the `PartnerAccountTrackerIdentifier` object for a given Partner and Auth/Tracker.
    *   *Args*: `partner` (PartnerAccount object), `auth_context` (ApiAuthID object, Tracker object, or None).
    *   *Returns*: `PartnerAccountTrackerIdentifier` object (or None).
    *   *Usage*: `get_partner_tracker_identifiers(publisher, auth).account_id_in_tracker`

*   `generate_pub_links(my_campaign_url, geo_code, traffic_type, config)`: Generates publisher links dynamically based on a PublisherConfig object.
    *   *Args*: `config` is a dictionary from `PublisherConfig.config`.
    *   *Returns*: List of dictionaries based on Cartesian product of active parameters.

## Operators
*   Math: `+`, `-`, `*`, `/`, `//` (floor div), `%` (modulo), `**` (power).
*   Logic: `and`, `or`, `not`.
*   Comparison: `==`, `!=`, `>`, `<`, `>=`, `<=`.
*   Ternary: `value_if_true if condition else value_if_false`
