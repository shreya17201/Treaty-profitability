-- 01 Portfolio summary by year
-- Shows: GROUP BY, aggregation, a computed ratio, and FILTER to count a subset in the same pass.

SELECT
    year,
    COUNT(*)                                                        AS treaties,
    ROUND(SUM(premium_earned) / 1e6, 1)                             AS premium_m,
    ROUND(SUM(claims_paid)    / 1e6, 1)                             AS claims_m,
    ROUND(SUM(claims_paid) / SUM(premium_earned), 3)                AS portfolio_loss_ratio,   -- premium-weighted
    COUNT(*) FILTER (WHERE claims_paid / premium_earned > 1.0)      AS treaties_above_1,
    ROUND(100.0 * COUNT(*) FILTER (WHERE claims_paid / premium_earned > 1.0) / COUNT(*), 1)
                                                                    AS pct_above_1
FROM treaty_year
GROUP BY year
ORDER BY year;
