-- Read-only access for the retail-lakehouse-qa app (dashboards, Data Explorer, Ask AI).
-- Principal: the app's service principal "app-37mmg2 retail-lakehouse-qa"
--            (application id d1a24843-76ea-48a7-a1f1-fe39b62de221).
--
-- Grants are read/query only — no MODIFY, CREATE or ALL PRIVILEGES. Granting on a catalog
-- is inherited by every current AND future schema, table, view, volume and function in it.
-- Run as the catalog owner (or a metastore admin) in a SQL editor / notebook.

GRANT USE CATALOG, USE SCHEMA, SELECT, EXECUTE, READ VOLUME, BROWSE ON CATALOG `retail_dev`               TO `d1a24843-76ea-48a7-a1f1-fe39b62de221`;
GRANT USE CATALOG, USE SCHEMA, SELECT, EXECUTE, READ VOLUME, BROWSE ON CATALOG `retail_staging`           TO `d1a24843-76ea-48a7-a1f1-fe39b62de221`;
GRANT USE CATALOG, USE SCHEMA, SELECT, EXECUTE, READ VOLUME, BROWSE ON CATALOG `retail_prod`              TO `d1a24843-76ea-48a7-a1f1-fe39b62de221`;
GRANT USE CATALOG, USE SCHEMA, SELECT, EXECUTE, READ VOLUME, BROWSE ON CATALOG `retail_data`              TO `d1a24843-76ea-48a7-a1f1-fe39b62de221`;
GRANT USE CATALOG, USE SCHEMA, SELECT, EXECUTE, READ VOLUME, BROWSE ON CATALOG `main`                     TO `d1a24843-76ea-48a7-a1f1-fe39b62de221`;
GRANT USE CATALOG, USE SCHEMA, SELECT, EXECUTE, READ VOLUME, BROWSE ON CATALOG `workspace`                TO `d1a24843-76ea-48a7-a1f1-fe39b62de221`;
GRANT USE CATALOG, USE SCHEMA, SELECT, EXECUTE, READ VOLUME, BROWSE ON CATALOG `apps`                     TO `d1a24843-76ea-48a7-a1f1-fe39b62de221`;
GRANT USE CATALOG, USE SCHEMA, SELECT, EXECUTE, READ VOLUME, BROWSE ON CATALOG `ci_cd`                    TO `d1a24843-76ea-48a7-a1f1-fe39b62de221`;
GRANT USE CATALOG, USE SCHEMA, SELECT, EXECUTE, READ VOLUME, BROWSE ON CATALOG `practice`                 TO `d1a24843-76ea-48a7-a1f1-fe39b62de221`;
GRANT USE CATALOG, USE SCHEMA, SELECT, EXECUTE, READ VOLUME, BROWSE ON CATALOG `dqx_demo`                 TO `d1a24843-76ea-48a7-a1f1-fe39b62de221`;
GRANT USE CATALOG, USE SCHEMA, SELECT, EXECUTE, READ VOLUME, BROWSE ON CATALOG `jet_blue`                 TO `d1a24843-76ea-48a7-a1f1-fe39b62de221`;
GRANT USE CATALOG, USE SCHEMA, SELECT, EXECUTE, READ VOLUME, BROWSE ON CATALOG `jet_blue_stream`          TO `d1a24843-76ea-48a7-a1f1-fe39b62de221`;
GRANT USE CATALOG, USE SCHEMA, SELECT, EXECUTE, READ VOLUME, BROWSE ON CATALOG `bakehouse_analytics_dev`  TO `d1a24843-76ea-48a7-a1f1-fe39b62de221`;
GRANT USE CATALOG, USE SCHEMA, SELECT, EXECUTE, READ VOLUME, BROWSE ON CATALOG `bakehouse_analytics_prod` TO `d1a24843-76ea-48a7-a1f1-fe39b62de221`;
GRANT USE CATALOG, USE SCHEMA, SELECT, EXECUTE, READ VOLUME, BROWSE ON CATALOG `ml_test`                  TO `d1a24843-76ea-48a7-a1f1-fe39b62de221`;
GRANT USE CATALOG, USE SCHEMA, SELECT, EXECUTE, READ VOLUME, BROWSE ON CATALOG `unity_catalog_testing`    TO `d1a24843-76ea-48a7-a1f1-fe39b62de221`;

-- Optional: the built-in `samples` catalog is already readable by everyone.
-- `system` (billing / audit logs) is intentionally NOT included — add it only if the app should see it.

-- Verify:
SHOW GRANTS `d1a24843-76ea-48a7-a1f1-fe39b62de221` ON CATALOG `retail_prod`;
