-- Access for external user andrew.sitz@datavail.com (retail-lakehouse-qa app + SQL).
-- The app runs SQL as the signed-in viewer (user authorization, `sql` scope), so these Unity Catalog
-- grants decide what he sees. He has the same read access as the owner on every user catalog.
-- (`samples` is readable by all account users already; `system` is NOT granted.)
-- Run as the catalog owner / workspace admin.

GRANT USE CATALOG, USE SCHEMA, SELECT, EXECUTE, READ VOLUME, BROWSE ON CATALOG `apps`                     TO `andrew.sitz@datavail.com`;
GRANT USE CATALOG, USE SCHEMA, SELECT, EXECUTE, READ VOLUME, BROWSE ON CATALOG `bakehouse_analytics_dev`  TO `andrew.sitz@datavail.com`;
GRANT USE CATALOG, USE SCHEMA, SELECT, EXECUTE, READ VOLUME, BROWSE ON CATALOG `bakehouse_analytics_prod` TO `andrew.sitz@datavail.com`;
GRANT USE CATALOG, USE SCHEMA, SELECT, EXECUTE, READ VOLUME, BROWSE ON CATALOG `ci_cd`                    TO `andrew.sitz@datavail.com`;
GRANT USE CATALOG, USE SCHEMA, SELECT, EXECUTE, READ VOLUME, BROWSE ON CATALOG `dqx_demo`                 TO `andrew.sitz@datavail.com`;
GRANT USE CATALOG, USE SCHEMA, SELECT, EXECUTE, READ VOLUME, BROWSE ON CATALOG `jet_blue`                 TO `andrew.sitz@datavail.com`;
GRANT USE CATALOG, USE SCHEMA, SELECT, EXECUTE, READ VOLUME, BROWSE ON CATALOG `jet_blue_stream`          TO `andrew.sitz@datavail.com`;
GRANT USE CATALOG, USE SCHEMA, SELECT, EXECUTE, READ VOLUME, BROWSE ON CATALOG `main`                     TO `andrew.sitz@datavail.com`;
GRANT USE CATALOG, USE SCHEMA, SELECT, EXECUTE, READ VOLUME, BROWSE ON CATALOG `ml_test`                  TO `andrew.sitz@datavail.com`;
GRANT USE CATALOG, USE SCHEMA, SELECT, EXECUTE, READ VOLUME, BROWSE ON CATALOG `practice`                 TO `andrew.sitz@datavail.com`;
GRANT USE CATALOG, USE SCHEMA, SELECT, EXECUTE, READ VOLUME, BROWSE ON CATALOG `retail_data`              TO `andrew.sitz@datavail.com`;
GRANT USE CATALOG, USE SCHEMA, SELECT, EXECUTE, READ VOLUME, BROWSE ON CATALOG `retail_dev`               TO `andrew.sitz@datavail.com`;
GRANT USE CATALOG, USE SCHEMA, SELECT, EXECUTE, READ VOLUME, BROWSE ON CATALOG `retail_prod`              TO `andrew.sitz@datavail.com`;
GRANT USE CATALOG, USE SCHEMA, SELECT, EXECUTE, READ VOLUME, BROWSE ON CATALOG `retail_staging`           TO `andrew.sitz@datavail.com`;
GRANT USE CATALOG, USE SCHEMA, SELECT, EXECUTE, READ VOLUME, BROWSE ON CATALOG `unity_catalog_testing`    TO `andrew.sitz@datavail.com`;
GRANT USE CATALOG, USE SCHEMA, SELECT, EXECUTE, READ VOLUME, BROWSE ON CATALOG `workspace`                TO `andrew.sitz@datavail.com`;

-- Verify:
SHOW GRANTS `andrew.sitz@datavail.com` ON CATALOG `jet_blue`;
