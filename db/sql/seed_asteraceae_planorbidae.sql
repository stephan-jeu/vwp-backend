-- Seed for Asteraceae (Glad biggenkruid) and Planorbidae (Platte schijfhoren)
SET statement_timeout = 0;
INSERT INTO families (name, priority) VALUES ('Asteraceae', 5) ON CONFLICT (name) DO NOTHING;
INSERT INTO families (name, priority) VALUES ('Planorbidae', 5) ON CONFLICT (name) DO NOTHING;
INSERT INTO species (family_id, name, name_latin) VALUES ((SELECT id FROM families WHERE name = 'Asteraceae'), 'Glad biggenkruid', NULL) ON CONFLICT (name) DO NOTHING;
INSERT INTO species (family_id, name, name_latin) VALUES ((SELECT id FROM families WHERE name = 'Planorbidae'), 'Platte schijfhoren', NULL) ON CONFLICT (name) DO NOTHING;
INSERT INTO functions (name) VALUES ('Groeiplaats') ON CONFLICT (name) DO NOTHING;
INSERT INTO functions (name) VALUES ('Leefgebied') ON CONFLICT (name) DO NOTHING;
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit, special_follow_up_action) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Asteraceae' AND s.name = 'Glad biggenkruid'), (SELECT id FROM functions WHERE name = 'Groeiplaats'), 2, 2.0, 21, 'dagen', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '''s Ochtends', NULL, NULL, false, false, false, false, NULL);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  (1, DATE '2000-07-01', DATE '2000-09-30', true, NULL),
  (2, DATE '2000-07-01', DATE '2000-09-30', true, NULL)
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Asteraceae' AND s.name = 'Glad biggenkruid') AND function_id = (SELECT id FROM functions WHERE name = 'Groeiplaats') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit, special_follow_up_action) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Planorbidae' AND s.name = 'Platte schijfhoren'), (SELECT id FROM functions WHERE name = 'Leefgebied'), 1, 2.0, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'Overdag', NULL, 'Bij voorkeur niet na (hevige) regenbuien', false, false, false, false, NULL);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  (1, DATE '2000-06-01', DATE '2000-09-30', true, NULL)
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Planorbidae' AND s.name = 'Platte schijfhoren') AND function_id = (SELECT id FROM functions WHERE name = 'Leefgebied') ORDER BY id DESC LIMIT 1) AS p(id);
