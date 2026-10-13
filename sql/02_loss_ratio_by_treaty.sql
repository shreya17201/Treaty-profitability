-- 02 Loss ratio by treaty and year, with a running average and the year-on-year change
-- Shows: window functions. PARTITION BY restarts the calculation for each treaty;
-- ORDER BY year makes AVG a running (cumulative) average and tells LAG which row is "previous".

WITH yearly AS (
    SELECT
        treaty_id,
        year,
        claims_paid / premium_earned AS loss_ratio
    FROM treaty_year
)
SELECT
    treaty_id,
    year,
    ROUND(loss_ratio, 3)                                                        AS loss_ratio,
    ROUND(AVG(loss_ratio) OVER (PARTITION BY treaty_id ORDER BY year
                                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 3)
                                                                                AS running_avg_loss_ratio,
    ROUND(loss_ratio - LAG(loss_ratio) OVER (PARTITION BY treaty_id ORDER BY year), 3)
                                                                                AS change_vs_last_year
FROM yearly
ORDER BY treaty_id, year;
