-- Seed generated for family Vlinder protocols
SET statement_timeout = 0;
INSERT INTO families (name, priority) VALUES ('Vlinder', 5) ON CONFLICT (name) DO NOTHING;
INSERT INTO species (family_id, name, name_latin) VALUES ((SELECT id FROM families WHERE name = 'Vlinder'), 'Iepenpage', NULL) ON CONFLICT (name) DO NOTHING;
INSERT INTO species (family_id, name, name_latin) VALUES ((SELECT id FROM families WHERE name = 'Vlinder'), 'Grote vos', NULL) ON CONFLICT (name) DO NOTHING;
INSERT INTO species (family_id, name, name_latin) VALUES ((SELECT id FROM families WHERE name = 'Vlinder'), 'Teunisbloempijlstaart', NULL) ON CONFLICT (name) DO NOTHING;
INSERT INTO functions (name) VALUES ('Voortplantingsplaats') ON CONFLICT (name) DO NOTHING;
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit, special_follow_up_action) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vlinder' AND s.name = 'Iepenpage'), (SELECT id FROM functions WHERE name = 'Voortplantingsplaats'), 3, 2.0, 7, 'dagen', NULL, NULL, NULL, NULL, NULL, NULL, NULL, 4, 'droog', 'Tussen 10:00 en 15:00 starten (evt. om 09:00 starten als het dan al 22 graden is en zonnig)', NULL, 'Min. 15 tot 19 graden (<50% bewolking) of vanaf 20 graden (>50% bewolking)', false, false, false, false, NULL);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  (1, DATE '2000-06-01', DATE '2000-07-15', true, NULL),
  (2, DATE '2000-06-01', DATE '2000-07-15', true, NULL),
  (3, DATE '2000-06-01', DATE '2000-07-15', true, NULL)
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vlinder' AND s.name = 'Iepenpage') AND function_id = (SELECT id FROM functions WHERE name = 'Voortplantingsplaats') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit, special_follow_up_action) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vlinder' AND s.name = 'Grote vos'), (SELECT id FROM functions WHERE name = 'Voortplantingsplaats'), 3, 2.0, 7, 'dagen', NULL, NULL, NULL, NULL, NULL, NULL, NULL, 4, 'droog', 'Tussen 10:00 en 15:00 starten (evt. om 09:00 starten als het dan al 22 graden is en zonnig)', NULL, 'Min. 15 tot 19 graden (<50% bewolking) of vanaf 20 graden (>50% bewolking)', false, false, false, false, NULL);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  (1, DATE '2000-05-15', DATE '2000-06-15', true, NULL),
  (2, DATE '2000-05-15', DATE '2000-06-15', true, NULL),
  (3, DATE '2000-05-15', DATE '2000-06-15', true, NULL)
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vlinder' AND s.name = 'Grote vos') AND function_id = (SELECT id FROM functions WHERE name = 'Voortplantingsplaats') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit, special_follow_up_action) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vlinder' AND s.name = 'Teunisbloempijlstaart'), (SELECT id FROM functions WHERE name = 'Voortplantingsplaats'), 3, 2.0, 7, 'dagen', NULL, NULL, NULL, NULL, NULL, NULL, NULL, 4, 'droog', 'Tussen 10:00 en 15:00 starten (evt. om 09:00 starten als het dan al 22 graden is en zonnig)', NULL, 'Min. 15 tot 19 graden (<50% bewolking) of vanaf 20 graden (>50% bewolking)', false, false, false, false, NULL);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  (1, DATE '2000-07-01', DATE '2000-07-31', true, NULL),
  (2, DATE '2000-07-01', DATE '2000-07-31', true, NULL),
  (3, DATE '2000-08-01', DATE '2000-08-15', true, NULL)
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vlinder' AND s.name = 'Teunisbloempijlstaart') AND function_id = (SELECT id FROM functions WHERE name = 'Voortplantingsplaats') ORDER BY id DESC LIMIT 1) AS p(id);
