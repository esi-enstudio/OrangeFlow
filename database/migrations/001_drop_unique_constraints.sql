-- Drop unique constraints and indexes from field_forces table
-- These constraints were removed from the model but still exist in the database

-- Drop unique constraints
ALTER TABLE field_forces DROP CONSTRAINT IF EXISTS field_forces_pool_number_key;
ALTER TABLE field_forces DROP CONSTRAINT IF EXISTS field_forces_itop_number_key;
ALTER TABLE field_forces DROP CONSTRAINT IF EXISTS field_forces_personal_number_key;

-- Drop unique indexes
DROP INDEX IF EXISTS ix_field_forces_itop_number;
DROP INDEX IF EXISTS ix_field_forces_personal_number;