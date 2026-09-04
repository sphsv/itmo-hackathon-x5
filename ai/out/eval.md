# Offline eval персонализатора

> Синтетическая выборка. Метрика проверяет техническое соответствие известному сценарию, а не продуктовый uplift.

- Размер выборки: **30**
- Personalized behavior accuracy: **96.7%**
- One-size-fits-all baseline accuracy: **36.7%**
- Разница: **60.0 п.п.**
- Constraints pass rate: **100.0%**

| user_id | true | predicted | recommended | hit |
|---|---|---|---|---|
| u_ivanovy | хозяин | хозяин | rostomer | yes |
| u_dima | охотник | охотник | save_product | yes |
| u_001279 | хозяин | хозяин | rostomer | yes |
| u_000610 | хозяин | хозяин | rostomer | yes |
| u_000983 | хозяин | хозяин | rostomer | yes |
| u_001407 | хозяин | хозяин | rostomer | yes |
| u_000145 | хозяин | хозяин | rostomer | yes |
| u_000624 | хозяин | хозяин | rostomer | yes |
| u_000441 | хозяин | хозяин | rostomer | yes |
| u_001212 | хозяин | хозяин | rostomer | yes |
| u_000362 | хозяин | хозяин | rostomer | yes |
| u_001119 | хозяин | категорийный | rostomer | no |
| u_001801 | охотник | охотник | save_product | yes |
| u_000006 | охотник | охотник | save_product | yes |
| u_001885 | охотник | охотник | save_product | yes |
| u_000682 | охотник | охотник | save_product | yes |
| u_000244 | охотник | охотник | save_product | yes |
| u_000152 | охотник | охотник | save_product | yes |
| u_001906 | охотник | охотник | save_product | yes |
| u_001838 | охотник | охотник | save_product | yes |
| u_000949 | охотник | охотник | save_product | yes |
| u_000404 | охотник | охотник | save_product | yes |
| u_001032 | категорийный | категорийный | rostomer | yes |
| u_001383 | категорийный | категорийный | stage_mission | yes |
| u_001208 | категорийный | категорийный | rostomer | yes |
| u_001930 | категорийный | категорийный | rostomer | yes |
| u_000434 | категорийный | категорийный | rostomer | yes |
| u_001534 | категорийный | категорийный | rostomer | yes |
| u_001038 | категорийный | категорийный | rostomer | yes |
| u_000055 | категорийный | категорийный | rostomer | yes |
