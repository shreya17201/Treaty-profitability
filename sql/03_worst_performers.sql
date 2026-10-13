-- 03 The ten worst treaties by dollars lost (last three years)
-- Shows: CTEs (WITH), ROW_NUMBER to pick each treaty's latest three years, a join across both tables,
-- and RANK / NTILE to rank and bucket treaties.
--
-- Dollars lost = annual claims paid in excess of premium = (loss ratio - 1.0) x premium, floored at zero.
-- Same definition as notebook 03, so the two lists should agree.

WITH numbered AS (
    SELECT
        *,
        ROW_NUMBER() OVER (PARTITION BY treaty_id ORDER BY year DESC) AS recency   -- 1 = latest year
    FROM treaty_year
),
last_three AS (
    SELECT
        treaty_id,
        COUNT(*)            AS years_used,
        SUM(premium_earned) AS premium,
        SUM(claims_paid)    AS claims
    FROM numbered
    WHERE recency <= 3
    GROUP BY treaty_id
),
scored AS (
    SELECT
        l.treaty_id,
        t.cedent_name,
        t.line_of_business,
        t.treaty_type,
        l.claims / l.premium                                     AS avg_loss_ratio,
        l.premium / l.years_used                                 AS annual_premium,
        GREATEST(l.claims - l.premium, 0) / l.years_used         AS annual_dollars_lost
    FROM last_three AS l
    JOIN treaties   AS t USING (treaty_id)
)
SELECT
    RANK()  OVER (ORDER BY annual_dollars_lost DESC)             AS rank_by_dollars,
    NTILE(4) OVER (ORDER BY avg_loss_ratio DESC)                 AS loss_ratio_quartile,   -- 1 = worst quarter
    treaty_id,
    cedent_name,
    line_of_business,
    treaty_type,
    ROUND(avg_loss_ratio, 3)                                     AS avg_loss_ratio,
    ROUND(annual_premium / 1e6, 2)                               AS annual_premium_m,
    ROUND(annual_dollars_lost / 1e6, 2)                          AS annual_dollars_lost_m
FROM scored
ORDER BY rank_by_dollars
LIMIT 10;
