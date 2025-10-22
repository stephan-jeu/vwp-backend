-- Seed generated for family Leporidae (Haas, Konijn)
SET statement_timeout = 0;
INSERT INTO families (name, priority) VALUES ('Leporidae', 5) ON CONFLICT (name) DO NOTHING;
INSERT INTO species (family_id, name, name_latin) VALUES ((SELECT id FROM families WHERE name = 'Leporidae'), 'Haas', NULL) ON CONFLICT (name) DO NOTHING;
INSERT INTO species (family_id, name, name_latin) VALUES ((SELECT id FROM families WHERE name = 'Leporidae'), 'Konijn', NULL) ON CONFLICT (name) DO NOTHING;
INSERT INTO functions (name) VALUES ('Voortplantingsplaats') ON CONFLICT (name) DO NOTHING;
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit, special_follow_up_action) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Leporidae' AND s.name = 'Haas'), (SELECT id FROM functions WHERE name = 'Voortplantingsplaats'), 2, 2.0, 10, 'dagen', 'sunset', 0, NULL, NULL, NULL, NULL, NULL, 4, 'droog', NULL, NULL, 'Geen mist, sneeuwval. Bodemtemperatuur < 15 graden', false, false, false, false, NULL);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  (1, DATE '2000-02-01', DATE '2000-10-31', true, NULL),
  (2, DATE '2000-04-01', DATE '2000-07-31', true, NULL)
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Leporidae' AND s.name = 'Haas') AND function_id = (SELECT id FROM functions WHERE name = 'Voortplantingsplaats') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit, special_follow_up_action) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Leporidae' AND s.name = 'Konijn'), (SELECT id FROM functions WHERE name = 'Voortplantingsplaats'), 2, 2.0, 10, 'dagen', 'sunset', 0, NULL, NULL, NULL, NULL, NULL, 4, 'droog', NULL, NULL, 'Geen mist, sneeuwval. Bodemtemperatuur < 15 graden', false, false, false, false, NULL);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  (1, DATE '2000-02-01', DATE '2000-10-31', true, NULL),
  (2, DATE '2000-04-01', DATE '2000-07-31', true, NULL)
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Leporidae' AND s.name = 'Konijn') AND function_id = (SELECT id FROM functions WHERE name = 'Voortplantingsplaats') ORDER BY id DESC LIMIT 1) AS p(id);
