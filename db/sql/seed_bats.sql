-- Seed generated from protocols/bats.json
SET statement_timeout = 0;
INSERT INTO families (name, priority) VALUES ('Vleermuis', 5) ON CONFLICT (name) DO NOTHING;
INSERT INTO species (family_id, name, name_latin, abbreviation) VALUES ((SELECT id FROM families WHERE name = 'Vleermuis'), 'Ruige dwergvleermuis', 'Pipistrellus nathusii', 'RD') ON CONFLICT (name) DO NOTHING;
INSERT INTO species (family_id, name, name_latin, abbreviation) VALUES ((SELECT id FROM families WHERE name = 'Vleermuis'), 'Gewone dwergvleermuis', 'Pipistrellus pipistrellus', 'GD') ON CONFLICT (name) DO NOTHING;
INSERT INTO species (family_id, name, name_latin, abbreviation) VALUES ((SELECT id FROM families WHERE name = 'Vleermuis'), 'Kleine dwergvleermuis', 'Pipistrellus pygmeus', 'KD') ON CONFLICT (name) DO NOTHING;
INSERT INTO species (family_id, name, name_latin, abbreviation) VALUES ((SELECT id FROM families WHERE name = 'Vleermuis'), 'Gewone grootoorvleermuis', 'Plecotus auritus', 'GeG') ON CONFLICT (name) DO NOTHING;
INSERT INTO species (family_id, name, name_latin, abbreviation) VALUES ((SELECT id FROM families WHERE name = 'Vleermuis'), 'Grijze grootoorvleermuis', 'Plecotus austriacus', 'GrG') ON CONFLICT (name) DO NOTHING;
INSERT INTO species (family_id, name, name_latin, abbreviation) VALUES ((SELECT id FROM families WHERE name = 'Vleermuis'), 'Tweekleurige vleermuis', 'Vespertilio murinus', 'TV') ON CONFLICT (name) DO NOTHING;
INSERT INTO species (family_id, name, name_latin, abbreviation) VALUES ((SELECT id FROM families WHERE name = 'Vleermuis'), 'Laatvlieger', 'Eptesicus serotinus', 'LV') ON CONFLICT (name) DO NOTHING;
INSERT INTO species (family_id, name, name_latin, abbreviation) VALUES ((SELECT id FROM families WHERE name = 'Vleermuis'), 'Rosse vleermuis', 'Nyctalus noctula', 'RV') ON CONFLICT (name) DO NOTHING;
INSERT INTO species (family_id, name, name_latin, abbreviation) VALUES ((SELECT id FROM families WHERE name = 'Vleermuis'), 'Bosvleermuis', 'Nyctalus leisleri', 'BoV') ON CONFLICT (name) DO NOTHING;
INSERT INTO species (family_id, name, name_latin, abbreviation) VALUES ((SELECT id FROM families WHERE name = 'Vleermuis'), 'Baardvleermuis', 'Myotis mystacinus', 'BaV') ON CONFLICT (name) DO NOTHING;
INSERT INTO species (family_id, name, name_latin, abbreviation) VALUES ((SELECT id FROM families WHERE name = 'Vleermuis'), 'Bechstein''s vleermuis', 'Myotis bechsteinii', 'BeV') ON CONFLICT (name) DO NOTHING;
INSERT INTO species (family_id, name, name_latin, abbreviation) VALUES ((SELECT id FROM families WHERE name = 'Vleermuis'), 'Brandt''s vleermuis', 'Myotis brandtii', 'BrV') ON CONFLICT (name) DO NOTHING;
INSERT INTO species (family_id, name, name_latin, abbreviation) VALUES ((SELECT id FROM families WHERE name = 'Vleermuis'), 'Franjestaart', 'Myotis nattereri', 'FS') ON CONFLICT (name) DO NOTHING;
INSERT INTO species (family_id, name, name_latin, abbreviation) VALUES ((SELECT id FROM families WHERE name = 'Vleermuis'), 'Ingekorven vleermuis', 'Myotis emarginatus', 'IV') ON CONFLICT (name) DO NOTHING;
INSERT INTO species (family_id, name, name_latin, abbreviation) VALUES ((SELECT id FROM families WHERE name = 'Vleermuis'), 'Meervleermuis', 'Myotis dasycneme', 'MV') ON CONFLICT (name) DO NOTHING;
INSERT INTO species (family_id, name, name_latin, abbreviation) VALUES ((SELECT id FROM families WHERE name = 'Vleermuis'), 'Watervleermuis', 'Myotis daubentonii', 'WV') ON CONFLICT (name) DO NOTHING;
INSERT INTO species (family_id, name, name_latin, abbreviation) VALUES ((SELECT id FROM families WHERE name = 'Vleermuis'), 'Vale vleermuis', 'Myotis myotis', 'VV') ON CONFLICT (name) DO NOTHING;
INSERT INTO functions (name) VALUES ('Winterverblijfplaats') ON CONFLICT (name) DO NOTHING;
INSERT INTO functions (name) VALUES ('Massawinterverblijfplaats') ON CONFLICT (name) DO NOTHING;
INSERT INTO functions (name) VALUES ('Kraamverblijfplaats') ON CONFLICT (name) DO NOTHING;
INSERT INTO functions (name) VALUES ('Zomerverblijfplaats') ON CONFLICT (name) DO NOTHING;
INSERT INTO functions (name) VALUES ('Satellietverblijf') ON CONFLICT (name) DO NOTHING;
INSERT INTO functions (name) VALUES ('Paarverblijf') ON CONFLICT (name) DO NOTHING;
INSERT INTO functions (name) VALUES ('Vliegroute') ON CONFLICT (name) DO NOTHING;
INSERT INTO functions (name) VALUES ('Migratieroute') ON CONFLICT (name) DO NOTHING;
INSERT INTO functions (name) VALUES ('Foerageergebied') ON CONFLICT (name) DO NOTHING;
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Pipistrellus nathusii'), (SELECT id FROM functions WHERE name = 'Winterverblijfplaats'), 1, NULL, NULL, NULL, 'DAYTIME', NULL, NULL, NULL, NULL, NULL, 0, NULL, NULL, NULL, NULL, NULL, false, false, false, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-12-01', DATE '2000-12-31', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Pipistrellus nathusii') AND function_id = (SELECT id FROM functions WHERE name = 'Winterverblijfplaats') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Pipistrellus pipistrellus'), (SELECT id FROM functions WHERE name = 'Winterverblijfplaats'), 1, NULL, NULL, NULL, 'DAYTIME', NULL, NULL, NULL, NULL, NULL, 0, NULL, NULL, NULL, NULL, NULL, false, false, false, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-12-01', DATE '2000-12-31', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Pipistrellus pipistrellus') AND function_id = (SELECT id FROM functions WHERE name = 'Winterverblijfplaats') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Pipistrellus pygmeus'), (SELECT id FROM functions WHERE name = 'Winterverblijfplaats'), 1, NULL, NULL, NULL, 'DAYTIME', NULL, NULL, NULL, NULL, NULL, 0, NULL, NULL, NULL, NULL, NULL, false, false, false, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-12-01', DATE '2000-12-31', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Pipistrellus pygmeus') AND function_id = (SELECT id FROM functions WHERE name = 'Winterverblijfplaats') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Plecotus auritus'), (SELECT id FROM functions WHERE name = 'Winterverblijfplaats'), 1, NULL, NULL, NULL, 'DAYTIME', NULL, NULL, NULL, NULL, NULL, 2, NULL, NULL, NULL, NULL, NULL, false, false, false, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-11-01', DATE '2000-12-31', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Plecotus auritus') AND function_id = (SELECT id FROM functions WHERE name = 'Winterverblijfplaats') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Plecotus austriacus'), (SELECT id FROM functions WHERE name = 'Winterverblijfplaats'), 1, NULL, NULL, NULL, 'DAYTIME', NULL, NULL, NULL, NULL, NULL, 2, NULL, NULL, NULL, NULL, NULL, false, false, false, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-11-01', DATE '2000-12-31', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Plecotus austriacus') AND function_id = (SELECT id FROM functions WHERE name = 'Winterverblijfplaats') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Vespertilio murinus'), (SELECT id FROM functions WHERE name = 'Winterverblijfplaats'), 1, NULL, NULL, NULL, 'DAYTIME', NULL, NULL, NULL, NULL, NULL, 2, NULL, NULL, NULL, NULL, NULL, false, false, false, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-10-15', DATE '2000-12-31', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Vespertilio murinus') AND function_id = (SELECT id FROM functions WHERE name = 'Winterverblijfplaats') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Eptesicus serotinus'), (SELECT id FROM functions WHERE name = 'Winterverblijfplaats'), 1, NULL, NULL, NULL, 'DAYTIME', NULL, NULL, NULL, NULL, NULL, 0, NULL, NULL, NULL, NULL, NULL, false, false, false, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-12-01', DATE '2000-12-31', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Eptesicus serotinus') AND function_id = (SELECT id FROM functions WHERE name = 'Winterverblijfplaats') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Nyctalus noctula'), (SELECT id FROM functions WHERE name = 'Winterverblijfplaats'), 1, NULL, NULL, NULL, 'DAYTIME', NULL, NULL, NULL, NULL, NULL, 0, NULL, NULL, NULL, NULL, NULL, false, false, false, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-12-01', DATE '2000-12-31', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Nyctalus noctula') AND function_id = (SELECT id FROM functions WHERE name = 'Winterverblijfplaats') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Nyctalus leisleri'), (SELECT id FROM functions WHERE name = 'Winterverblijfplaats'), 1, NULL, NULL, NULL, 'DAYTIME', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, false, false, false, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-12-01', DATE '2000-12-31', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Nyctalus leisleri') AND function_id = (SELECT id FROM functions WHERE name = 'Winterverblijfplaats') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis mystacinus'), (SELECT id FROM functions WHERE name = 'Winterverblijfplaats'), 1, NULL, NULL, NULL, 'DAYTIME', NULL, NULL, NULL, NULL, NULL, 1, NULL, NULL, NULL, NULL, NULL, false, false, false, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-12-01', DATE '2000-12-31', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis mystacinus') AND function_id = (SELECT id FROM functions WHERE name = 'Winterverblijfplaats') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis bechsteinii'), (SELECT id FROM functions WHERE name = 'Winterverblijfplaats'), 1, NULL, NULL, NULL, 'DAYTIME', NULL, NULL, NULL, NULL, NULL, 2, NULL, NULL, NULL, NULL, NULL, false, false, false, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-12-01', DATE '2000-12-31', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis bechsteinii') AND function_id = (SELECT id FROM functions WHERE name = 'Winterverblijfplaats') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis brandtii'), (SELECT id FROM functions WHERE name = 'Winterverblijfplaats'), 1, NULL, NULL, NULL, 'DAYTIME', NULL, NULL, NULL, NULL, NULL, 1, NULL, NULL, NULL, NULL, NULL, false, false, false, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-12-01', DATE '2000-12-31', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis brandtii') AND function_id = (SELECT id FROM functions WHERE name = 'Winterverblijfplaats') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis nattereri'), (SELECT id FROM functions WHERE name = 'Winterverblijfplaats'), 1, NULL, NULL, NULL, 'DAYTIME', NULL, NULL, NULL, NULL, NULL, 1, NULL, NULL, NULL, NULL, NULL, false, false, false, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-12-01', DATE '2000-12-31', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis nattereri') AND function_id = (SELECT id FROM functions WHERE name = 'Winterverblijfplaats') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis emarginatus'), (SELECT id FROM functions WHERE name = 'Winterverblijfplaats'), 1, NULL, NULL, NULL, 'DAYTIME', NULL, NULL, NULL, NULL, NULL, 2, NULL, NULL, NULL, NULL, NULL, false, false, false, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-12-01', DATE '2000-12-31', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis emarginatus') AND function_id = (SELECT id FROM functions WHERE name = 'Winterverblijfplaats') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis dasycneme'), (SELECT id FROM functions WHERE name = 'Winterverblijfplaats'), 1, NULL, NULL, NULL, 'DAYTIME', NULL, NULL, NULL, NULL, NULL, NULL, '3', NULL, NULL, NULL, NULL, false, false, false, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-12-01', DATE '2000-12-31', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis dasycneme') AND function_id = (SELECT id FROM functions WHERE name = 'Winterverblijfplaats') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis daubentonii'), (SELECT id FROM functions WHERE name = 'Winterverblijfplaats'), 1, NULL, NULL, NULL, 'DAYTIME', NULL, NULL, NULL, NULL, NULL, 1, NULL, NULL, NULL, NULL, NULL, false, false, false, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-12-01', DATE '2000-12-31', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis daubentonii') AND function_id = (SELECT id FROM functions WHERE name = 'Winterverblijfplaats') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis myotis'), (SELECT id FROM functions WHERE name = 'Winterverblijfplaats'), 1, NULL, NULL, NULL, 'DAYTIME', NULL, NULL, NULL, NULL, NULL, 2, NULL, NULL, NULL, NULL, NULL, false, false, false, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-12-01', DATE '2000-12-31', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis myotis') AND function_id = (SELECT id FROM functions WHERE name = 'Winterverblijfplaats') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Pipistrellus pipistrellus'), (SELECT id FROM functions WHERE name = 'Massawinterverblijfplaats'), 2, 2, 10, 'days', 'ABSOLUTE_TIME', NULL, '00:00:00', '02:00:00', NULL, NULL, 13, 3, 'geen regen', NULL, NULL, '2 x 2 uur', false, false, false, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-08-01', DATE '2000-09-10', true, NULL ),
  ( 2, DATE '2000-08-01', DATE '2000-09-10', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Pipistrellus pipistrellus') AND function_id = (SELECT id FROM functions WHERE name = 'Massawinterverblijfplaats') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Pipistrellus nathusii'), (SELECT id FROM functions WHERE name = 'Kraamverblijfplaats'), 2, 2, 20, 'days', 'SUNSET', 0, NULL, NULL, 'SUNRISE', 0, 10, 4, 'motregen', NULL, NULL, '2 x 2 uur waarvan 1 ronde in juni', false, false, true, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-05-15', DATE '2000-07-15', true, NULL ),
  ( 2, DATE '2000-05-15', DATE '2000-07-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Pipistrellus nathusii') AND function_id = (SELECT id FROM functions WHERE name = 'Kraamverblijfplaats') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Pipistrellus pipistrellus'), (SELECT id FROM functions WHERE name = 'Kraamverblijfplaats'), 2, 2, 20, 'days', 'SUNSET', 0, NULL, NULL, 'SUNRISE', 0, 10, 4, 'motregen', NULL, NULL, '2 x 2 uur waarvan 1 ronde in juni', false, false, true, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-05-15', DATE '2000-07-15', true, NULL ),
  ( 2, DATE '2000-05-15', DATE '2000-07-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Pipistrellus pipistrellus') AND function_id = (SELECT id FROM functions WHERE name = 'Kraamverblijfplaats') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Pipistrellus pygmeus'), (SELECT id FROM functions WHERE name = 'Kraamverblijfplaats'), 2, 2, 20, 'days', 'SUNSET', 0, NULL, NULL, 'SUNRISE', 0, 10, 4, 'motregen', NULL, NULL, '2 x 2 uur waarvan 1 ronde in juni', false, false, true, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-05-15', DATE '2000-07-15', true, NULL ),
  ( 2, DATE '2000-05-15', DATE '2000-07-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Pipistrellus pygmeus') AND function_id = (SELECT id FROM functions WHERE name = 'Kraamverblijfplaats') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Plecotus auritus'), (SELECT id FROM functions WHERE name = 'Kraamverblijfplaats'), 2, 2, 20, 'days', 'SUNSET', 30, NULL, NULL, 'SUNRISE', 60, 5, 2, 'geen regen', '[maximaal donker]', NULL, '2 x 2 uur waarvan 1 ronde in juni', false, false, true, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-05-15', DATE '2000-07-15', true, NULL ),
  ( 2, DATE '2000-05-15', DATE '2000-07-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Plecotus auritus') AND function_id = (SELECT id FROM functions WHERE name = 'Kraamverblijfplaats') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Plecotus austriacus'), (SELECT id FROM functions WHERE name = 'Kraamverblijfplaats'), 2, 2, 20, 'days', 'SUNSET', 30, NULL, NULL, 'SUNRISE', 60, 5, 2, 'geen regen', '[maximaal donker]', NULL, '2 x 2 uur waarvan 1 ronde in juni', false, false, true, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-06-01', DATE '2000-07-15', true, NULL ),
  ( 2, DATE '2000-06-01', DATE '2000-07-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Plecotus austriacus') AND function_id = (SELECT id FROM functions WHERE name = 'Kraamverblijfplaats') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Vespertilio murinus'), (SELECT id FROM functions WHERE name = 'Kraamverblijfplaats'), 2, 2, 20, 'days', 'SUNSET', 0, NULL, NULL, 'SUNRISE', 60, 10, 4, 'motregen', NULL, NULL, '2 x 2 uur, ''s avonds waarvan 1 ronde in juni', false, true, true, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-05-15', DATE '2000-07-15', true, NULL ),
  ( 2, DATE '2000-05-15', DATE '2000-07-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Vespertilio murinus') AND function_id = (SELECT id FROM functions WHERE name = 'Kraamverblijfplaats') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Eptesicus serotinus'), (SELECT id FROM functions WHERE name = 'Kraamverblijfplaats'), 2, 2, 20, 'days', 'SUNSET', 0, NULL, NULL, NULL, NULL, 12, 4, 'motregen', NULL, NULL, '2 x 2 uur, ''s avonds waarvan 1 ronde in juni', false, true, true, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-05-15', DATE '2000-07-15', true, NULL ),
  ( 2, DATE '2000-05-15', DATE '2000-07-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Eptesicus serotinus') AND function_id = (SELECT id FROM functions WHERE name = 'Kraamverblijfplaats') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Nyctalus noctula'), (SELECT id FROM functions WHERE name = 'Kraamverblijfplaats'), 2, 2, 20, 'days', 'SUNSET', 0, NULL, NULL, 'SUNRISE', 30, 12, 4, 'motregen', NULL, NULL, '2 x 2 uur waarvan 1 ronde in juni', false, false, true, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-05-15', DATE '2000-07-15', true, NULL ),
  ( 2, DATE '2000-05-15', DATE '2000-07-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Nyctalus noctula') AND function_id = (SELECT id FROM functions WHERE name = 'Kraamverblijfplaats') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Nyctalus leisleri'), (SELECT id FROM functions WHERE name = 'Kraamverblijfplaats'), 2, 2, 20, 'days', 'SUNSET', 0, NULL, NULL, 'SUNRISE', 30, NULL, NULL, NULL, NULL, NULL, '2 x 2 uur waarvan 1 ronde in juni', false, false, true, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-05-15', DATE '2000-07-15', true, NULL ),
  ( 2, DATE '2000-05-15', DATE '2000-07-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Nyctalus leisleri') AND function_id = (SELECT id FROM functions WHERE name = 'Kraamverblijfplaats') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis mystacinus'), (SELECT id FROM functions WHERE name = 'Kraamverblijfplaats'), 2, 2, 20, 'days', 'SUNSET', 15, NULL, NULL, 'SUNRISE', 60, 10, 4, 'motregen', NULL, NULL, '2 x 2 uur, waarvan 1 ochtend * waarvan 1 ronde in juni', true, false, true, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-06-01', DATE '2000-07-15', true, NULL ),
  ( 2, DATE '2000-06-01', DATE '2000-07-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis mystacinus') AND function_id = (SELECT id FROM functions WHERE name = 'Kraamverblijfplaats') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis bechsteinii'), (SELECT id FROM functions WHERE name = 'Kraamverblijfplaats'), 2, 2, 20, 'days', 'SUNSET', 15, NULL, NULL, 'SUNRISE', 60, 10, 4, 'motregen', NULL, NULL, '2 x 2 uur, waarvan 1 ochtend * waarvan 1 ronde in juni', true, false, true, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-05-15', DATE '2000-07-15', true, NULL ),
  ( 2, DATE '2000-05-15', DATE '2000-07-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis bechsteinii') AND function_id = (SELECT id FROM functions WHERE name = 'Kraamverblijfplaats') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis brandtii'), (SELECT id FROM functions WHERE name = 'Kraamverblijfplaats'), 2, 2, 20, 'days', 'SUNSET', 15, NULL, NULL, 'SUNRISE', 60, 10, 4, 'motregen', NULL, NULL, '2 x 2 uur, waarvan 1 ochtend * waarvan 1 ronde in juni', true, false, true, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-06-01', DATE '2000-07-15', true, NULL ),
  ( 2, DATE '2000-06-01', DATE '2000-07-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis brandtii') AND function_id = (SELECT id FROM functions WHERE name = 'Kraamverblijfplaats') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis nattereri'), (SELECT id FROM functions WHERE name = 'Kraamverblijfplaats'), 2, 2, 20, 'days', 'SUNSET', 15, NULL, NULL, 'SUNRISE', 60, 10, 4, 'motregen', NULL, NULL, '2 x 2 uur, waarvan 1 ochtend * waarvan 1 ronde in juni', true, false, true, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-06-01', DATE '2000-07-15', true, NULL ),
  ( 2, DATE '2000-06-01', DATE '2000-07-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis nattereri') AND function_id = (SELECT id FROM functions WHERE name = 'Kraamverblijfplaats') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis emarginatus'), (SELECT id FROM functions WHERE name = 'Kraamverblijfplaats'), 2, 2, 20, 'days', 'SUNSET', 15, NULL, NULL, 'SUNRISE', 60, 10, 4, 'motregen', NULL, NULL, '2 x 2 uur, waarvan 1 ochtend * waarvan 1 ronde in juni', true, false, true, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-06-01', DATE '2000-07-15', true, NULL ),
  ( 2, DATE '2000-06-01', DATE '2000-07-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis emarginatus') AND function_id = (SELECT id FROM functions WHERE name = 'Kraamverblijfplaats') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis dasycneme'), (SELECT id FROM functions WHERE name = 'Kraamverblijfplaats'), 2, 2, 15, 'days', 'SUNRISE', NULL, NULL, NULL, 'SUNRISE', 60, 8, 3, 'geen neerslag, geen mist boven watergangen', NULL, NULL, '2 x 2 uur*, enkel ochtend bezoeken, waarvan 1 ronde in juni.', true, false, true, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-05-15', DATE '2000-06-25', true, NULL ),
  ( 2, DATE '2000-05-15', DATE '2000-06-25', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis dasycneme') AND function_id = (SELECT id FROM functions WHERE name = 'Kraamverblijfplaats') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis daubentonii'), (SELECT id FROM functions WHERE name = 'Kraamverblijfplaats'), 2, 2, 20, 'days', 'SUNSET', 15, NULL, NULL, 'SUNRISE', 60, 10, 4, 'motregen', NULL, NULL, '2 x 2 uur, waarvan zo mogelijk 1 ochtend * waarvan 1 ronde in juni', true, false, true, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-06-01', DATE '2000-07-15', true, NULL ),
  ( 2, DATE '2000-06-01', DATE '2000-07-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis daubentonii') AND function_id = (SELECT id FROM functions WHERE name = 'Kraamverblijfplaats') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis myotis'), (SELECT id FROM functions WHERE name = 'Kraamverblijfplaats'), 2, 2, 20, 'days', 'SUNSET', 15, NULL, NULL, 'SUNRISE', 60, 10, 4, 'motregen', NULL, NULL, '2 x 2 uur, waarvan 1 ochtend * waarvan 1 ronde in juni', true, false, true, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-06-01', DATE '2000-07-15', true, NULL ),
  ( 2, DATE '2000-06-01', DATE '2000-07-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis myotis') AND function_id = (SELECT id FROM functions WHERE name = 'Kraamverblijfplaats') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Pipistrellus nathusii'), (SELECT id FROM functions WHERE name = 'Zomerverblijfplaats'), 2, 2, 20, 'days', 'SUNSET', 0, NULL, NULL, 'SUNRISE', 0, 8, 4, 'motregen', NULL, NULL, '2 x 2 uur, waarvan ten minste 1 ochtend* en 1 x in de kraamperiode', true, false, false, true);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-04-15', DATE '2000-08-15', true, NULL ),
  ( 2, DATE '2000-04-15', DATE '2000-08-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Pipistrellus nathusii') AND function_id = (SELECT id FROM functions WHERE name = 'Zomerverblijfplaats') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Pipistrellus pipistrellus'), (SELECT id FROM functions WHERE name = 'Zomerverblijfplaats'), 2, 2, 20, 'days', 'SUNSET', 0, NULL, NULL, 'SUNRISE', 0, 7, 4, 'motregen', NULL, NULL, '2 x 2 uur, waarvan ten minste 1 ochtend* en 1 x in de kraamperiode', true, false, false, true);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-04-15', DATE '2000-10-15', true, NULL ),
  ( 2, DATE '2000-04-15', DATE '2000-10-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Pipistrellus pipistrellus') AND function_id = (SELECT id FROM functions WHERE name = 'Zomerverblijfplaats') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Pipistrellus pygmeus'), (SELECT id FROM functions WHERE name = 'Zomerverblijfplaats'), 2, 2, 20, 'days', 'SUNSET', 0, NULL, NULL, 'SUNRISE', 0, 7, 4, 'motregen', NULL, NULL, '2 x 2 uur, waarvan ten minste 1 ochtend* en 1 x in de kraamperiode', true, false, false, true);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-04-15', DATE '2000-10-15', true, NULL ),
  ( 2, DATE '2000-04-15', DATE '2000-10-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Pipistrellus pygmeus') AND function_id = (SELECT id FROM functions WHERE name = 'Zomerverblijfplaats') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Plecotus auritus'), (SELECT id FROM functions WHERE name = 'Zomerverblijfplaats'), 2, 2, 20, 'days', 'SUNSET', 30, NULL, NULL, 'SUNRISE', 60, 5, 2, 'geen regen', '[maximaal donker]', NULL, '2 x 2 uur, waarvan ten minste 1 ochtend* en 1 x in de kraamperiode', true, false, false, true);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-04-15', DATE '2000-08-15', true, NULL ),
  ( 2, DATE '2000-04-15', DATE '2000-08-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Plecotus auritus') AND function_id = (SELECT id FROM functions WHERE name = 'Zomerverblijfplaats') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Plecotus austriacus'), (SELECT id FROM functions WHERE name = 'Zomerverblijfplaats'), 2, 2, 20, 'days', 'SUNSET', 30, NULL, NULL, 'SUNRISE', 60, 5, 2, 'geen regen', '[maximaal donker]', NULL, '2 x 2 uur, waarvan ten minste 1 ochtend* en 1 x in de kraamperiode', true, false, false, true);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-04-15', DATE '2000-08-15', true, NULL ),
  ( 2, DATE '2000-04-15', DATE '2000-08-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Plecotus austriacus') AND function_id = (SELECT id FROM functions WHERE name = 'Zomerverblijfplaats') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Vespertilio murinus'), (SELECT id FROM functions WHERE name = 'Zomerverblijfplaats'), 2, 2, 20, 'days', 'SUNSET', 0, NULL, NULL, 'SUNRISE', 60, 0, 4, 'motregen', NULL, NULL, '2 x 2 uur, waarvan ten minste 1 ochtend* en 1 x in de kraamperiode', true, false, false, true);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-05-15', DATE '2000-08-01', true, NULL ),
  ( 2, DATE '2000-05-15', DATE '2000-08-01', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Vespertilio murinus') AND function_id = (SELECT id FROM functions WHERE name = 'Zomerverblijfplaats') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Eptesicus serotinus'), (SELECT id FROM functions WHERE name = 'Zomerverblijfplaats'), 2, 2, 20, 'days', 'SUNSET', 0, NULL, NULL, NULL, NULL, 12, 4, 'motregen', NULL, NULL, '2 x 2 uur, ''s avonds* waarvan 1 x in de kraamperiode', false, true, false, true);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-05-15', DATE '2000-09-15', true, NULL ),
  ( 2, DATE '2000-05-15', DATE '2000-09-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Eptesicus serotinus') AND function_id = (SELECT id FROM functions WHERE name = 'Zomerverblijfplaats') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Nyctalus noctula'), (SELECT id FROM functions WHERE name = 'Zomerverblijfplaats'), 2, 2, 20, 'days', 'SUNSET', 0, NULL, NULL, 'SUNRISE', 30, 12, 4, 'motregen', NULL, NULL, '2 x 2 uur, waarvan ten minste 1 ochtend* en 1 x in de kraamperiode', true, false, false, true);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-05-15', DATE '2000-08-15', true, NULL ),
  ( 2, DATE '2000-05-15', DATE '2000-08-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Nyctalus noctula') AND function_id = (SELECT id FROM functions WHERE name = 'Zomerverblijfplaats') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Nyctalus leisleri'), (SELECT id FROM functions WHERE name = 'Zomerverblijfplaats'), 2, 2, 20, 'days', 'SUNSET', 0, NULL, NULL, 'SUNRISE', 30, NULL, NULL, NULL, NULL, NULL, '2 x 2 uur, waarvan ten minste 1 ochtend* en 1 x in de kraamperiode ', true, false, false, true);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-05-15', DATE '2000-08-15', true, NULL ),
  ( 2, DATE '2000-05-15', DATE '2000-08-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Nyctalus leisleri') AND function_id = (SELECT id FROM functions WHERE name = 'Zomerverblijfplaats') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis mystacinus'), (SELECT id FROM functions WHERE name = 'Zomerverblijfplaats'), 2, 2, 20, 'days', 'SUNSET', 15, NULL, NULL, 'SUNRISE', 60, 10, 4, 'motregen', NULL, NULL, '2 x 2 uur, waarvan ten minste 1 ochtend* en 1 x in de kraamperiode', true, false, false, true);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-05-15', DATE '2000-08-15', true, NULL ),
  ( 2, DATE '2000-05-15', DATE '2000-08-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis mystacinus') AND function_id = (SELECT id FROM functions WHERE name = 'Zomerverblijfplaats') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis bechsteinii'), (SELECT id FROM functions WHERE name = 'Zomerverblijfplaats'), 2, 2, 20, 'days', 'SUNSET', 15, NULL, NULL, 'SUNRISE', 60, 10, 4, 'motregen', NULL, NULL, '2 x 2 uur, waarvan ten minste 1 ochtend* en 1 x in de kraamperiode', true, false, false, true);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-05-15', DATE '2000-08-15', true, NULL ),
  ( 2, DATE '2000-05-15', DATE '2000-08-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis bechsteinii') AND function_id = (SELECT id FROM functions WHERE name = 'Zomerverblijfplaats') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis brandtii'), (SELECT id FROM functions WHERE name = 'Zomerverblijfplaats'), 2, 2, 20, 'days', 'SUNSET', 15, NULL, NULL, 'SUNRISE', 60, 10, 4, 'motregen', NULL, NULL, '2 x 2 uur, waarvan ten minste 1 ochtend* en 1 x in de kraamperiode', true, false, false, true);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-05-15', DATE '2000-08-15', true, NULL ),
  ( 2, DATE '2000-05-15', DATE '2000-08-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis brandtii') AND function_id = (SELECT id FROM functions WHERE name = 'Zomerverblijfplaats') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis nattereri'), (SELECT id FROM functions WHERE name = 'Zomerverblijfplaats'), 2, 2, 20, 'days', 'SUNSET', 15, NULL, NULL, 'SUNRISE', 60, 10, 4, 'motregen', NULL, NULL, '2 x 2 uur, waarvan ten minste 1 ochtend* en 1 x in de kraamperiode', true, false, false, true);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-05-15', DATE '2000-08-15', true, NULL ),
  ( 2, DATE '2000-05-15', DATE '2000-08-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis nattereri') AND function_id = (SELECT id FROM functions WHERE name = 'Zomerverblijfplaats') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis emarginatus'), (SELECT id FROM functions WHERE name = 'Zomerverblijfplaats'), 2, 2, 20, 'days', 'SUNSET', 15, NULL, NULL, 'SUNRISE', 60, 10, 4, 'motregen', NULL, NULL, '2 x 2 uur, waarvan ten minste 1 ochtend* en 1 x in de kraamperiode', true, false, false, true);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-05-15', DATE '2000-08-15', true, NULL ),
  ( 2, DATE '2000-05-15', DATE '2000-08-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis emarginatus') AND function_id = (SELECT id FROM functions WHERE name = 'Zomerverblijfplaats') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis dasycneme'), (SELECT id FROM functions WHERE name = 'Satellietverblijf'), 1, 3, NULL, NULL, 'SUNRISE', NULL, NULL, NULL, 'SUNRISE', 0, 8, 3, 'geen neerslag, geen mist boven watergangen', NULL, NULL, '1 x 2 uur ''s ochtends in omgeving van kraamgroepen en mannenverblijven (zie de bij het protocol gepubliceerde kaart).', true, false, false, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-07-01', DATE '2000-07-31', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis dasycneme') AND function_id = (SELECT id FROM functions WHERE name = 'Satellietverblijf') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis daubentonii'), (SELECT id FROM functions WHERE name = 'Zomerverblijfplaats'), 2, 2, 20, 'days', 'SUNSET', 15, NULL, NULL, 'SUNRISE', 60, 10, 4, 'motregen', NULL, NULL, '2 x 2 uur, waarvan ten minste 1 ochtend* en 1 x in de kraamperiode', true, false, false, true);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-04-15', DATE '2000-09-15', true, NULL ),
  ( 2, DATE '2000-04-15', DATE '2000-09-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis daubentonii') AND function_id = (SELECT id FROM functions WHERE name = 'Zomerverblijfplaats') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis myotis'), (SELECT id FROM functions WHERE name = 'Zomerverblijfplaats'), 2, 2, 20, 'days', 'SUNSET', 15, NULL, NULL, 'SUNRISE', 60, 10, 4, 'motregen', NULL, NULL, '2 x 2 uur, waarvan ten minste 1 ochtend* en 1 x in de kraamperiode', true, false, false, true);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-05-15', DATE '2000-08-15', true, NULL ),
  ( 2, DATE '2000-05-15', DATE '2000-08-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis myotis') AND function_id = (SELECT id FROM functions WHERE name = 'Zomerverblijfplaats') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Pipistrellus nathusii'), (SELECT id FROM functions WHERE name = 'Paarverblijf'), 2, 2, 20, 'days', 'SUNSET', 60, NULL, NULL, 'SUNRISE', 60, 8, 4, 'motregen', 'en minimaal 1 ronde rond middernacht', 'eerder bij kou', '2 x 2 uur', false, false, false, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-08-15', DATE '2000-10-01', true, NULL ),
  ( 2, DATE '2000-08-15', DATE '2000-10-01', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Pipistrellus nathusii') AND function_id = (SELECT id FROM functions WHERE name = 'Paarverblijf') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Pipistrellus pipistrellus'), (SELECT id FROM functions WHERE name = 'Paarverblijf'), 2, 2, 20, 'days', 'SUNSET', 60, NULL, NULL, 'SUNRISE', 0, 6, 4, 'motregen', NULL, 'eerder bij kou', '2 x 2 uur', false, false, false, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-08-15', DATE '2000-10-01', true, NULL ),
  ( 2, DATE '2000-08-15', DATE '2000-10-01', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Pipistrellus pipistrellus') AND function_id = (SELECT id FROM functions WHERE name = 'Paarverblijf') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Pipistrellus pygmeus'), (SELECT id FROM functions WHERE name = 'Paarverblijf'), 2, 2, 20, 'days', 'SUNSET', 60, NULL, NULL, 'SUNRISE', 0, 6, 4, 'motregen', NULL, 'eerder bij kou', '2 x 2 uur', false, false, false, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-08-15', DATE '2000-10-01', true, NULL ),
  ( 2, DATE '2000-08-15', DATE '2000-10-01', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Pipistrellus pygmeus') AND function_id = (SELECT id FROM functions WHERE name = 'Paarverblijf') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Plecotus auritus'), (SELECT id FROM functions WHERE name = 'Paarverblijf'), 2, 2, 20, 'days', 'SUNSET', 0, NULL, NULL, 'SUNRISE', 0, 5, 2, 'geen regen', '[maximaal donker]', NULL, '2 x 2 uur', false, false, false, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-08-15', DATE '2000-10-01', true, NULL ),
  ( 2, DATE '2000-08-15', DATE '2000-10-01', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Plecotus auritus') AND function_id = (SELECT id FROM functions WHERE name = 'Paarverblijf') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Plecotus austriacus'), (SELECT id FROM functions WHERE name = 'Paarverblijf'), 2, 2, 20, 'days', 'SUNSET', 0, NULL, NULL, 'SUNRISE', 0, 5, 2, 'geen regen', '[maximaal donker]', NULL, '2 x 2 uur', false, false, false, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-08-15', DATE '2000-10-01', true, NULL ),
  ( 2, DATE '2000-08-15', DATE '2000-10-01', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Plecotus austriacus') AND function_id = (SELECT id FROM functions WHERE name = 'Paarverblijf') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Vespertilio murinus'), (SELECT id FROM functions WHERE name = 'Paarverblijf'), 2, 2, 20, 'days', 'SUNSET', 30, NULL, NULL, 'SUNRISE', 0, 0, 4, 'motregen', NULL, NULL, '2 x 2 uur, waarvan tenminste 1 x ''s avonds', false, true, false, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-10-01', DATE '2000-12-01', true, NULL ),
  ( 2, DATE '2000-10-01', DATE '2000-12-01', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Vespertilio murinus') AND function_id = (SELECT id FROM functions WHERE name = 'Paarverblijf') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Eptesicus serotinus'), (SELECT id FROM functions WHERE name = 'Paarverblijf'), 2, 2, 20, 'days', 'SUNSET', 30, NULL, NULL, NULL, NULL, 12, 4, 'motregen', NULL, NULL, '2 x 2 uur, waarvan tenminste 1 x ''s avonds', false, true, false, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-08-01', DATE '2000-10-15', true, NULL ),
  ( 2, DATE '2000-08-01', DATE '2000-10-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Eptesicus serotinus') AND function_id = (SELECT id FROM functions WHERE name = 'Paarverblijf') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Nyctalus noctula'), (SELECT id FROM functions WHERE name = 'Paarverblijf'), 2, 2, 20, 'days', 'SUNSET', 60, NULL, NULL, 'SUNRISE', 60, 5, 4, 'motregen', NULL, NULL, '2 x 2 uur, waarvan tenminste 1 x ''s avonds', false, true, false, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-08-01', DATE '2000-09-15', true, NULL ),
  ( 2, DATE '2000-08-01', DATE '2000-09-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Nyctalus noctula') AND function_id = (SELECT id FROM functions WHERE name = 'Paarverblijf') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Nyctalus leisleri'), (SELECT id FROM functions WHERE name = 'Paarverblijf'), 2, 2, 20, 'days', 'SUNSET', 60, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2 x 2 uur', false, false, false, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-07-15', DATE '2000-09-01', true, NULL ),
  ( 2, DATE '2000-07-15', DATE '2000-09-01', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Nyctalus leisleri') AND function_id = (SELECT id FROM functions WHERE name = 'Paarverblijf') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis mystacinus'), (SELECT id FROM functions WHERE name = 'Paarverblijf'), 2, 2, 20, 'days', 'ABSOLUTE_TIME', 0, '22:00:00', '01:00:00', NULL, NULL, 5, 4, 'motregen', NULL, NULL, '2 x 2 uur', false, false, false, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-08-01', DATE '2000-09-15', true, NULL ),
  ( 2, DATE '2000-08-01', DATE '2000-09-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis mystacinus') AND function_id = (SELECT id FROM functions WHERE name = 'Paarverblijf') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis bechsteinii'), (SELECT id FROM functions WHERE name = 'Paarverblijf'), 2, 2, 20, 'days', 'ABSOLUTE_TIME', 0, '22:00:00', '01:00:00', NULL, NULL, 5, 4, 'motregen', NULL, NULL, '2 x 2 uur', false, false, false, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-09-01', DATE '2000-10-01', true, NULL ),
  ( 2, DATE '2000-09-01', DATE '2000-10-01', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis bechsteinii') AND function_id = (SELECT id FROM functions WHERE name = 'Paarverblijf') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis brandtii'), (SELECT id FROM functions WHERE name = 'Paarverblijf'), 2, 2, 10, 'days', 'ABSOLUTE_TIME', 0, '22:00:00', '01:00:00', NULL, NULL, 5, 4, 'motregen', NULL, NULL, '2 x 2 uur', false, false, false, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-08-01', DATE '2000-08-15', true, NULL ),
  ( 2, DATE '2000-08-01', DATE '2000-08-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis brandtii') AND function_id = (SELECT id FROM functions WHERE name = 'Paarverblijf') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis nattereri'), (SELECT id FROM functions WHERE name = 'Paarverblijf'), 2, 2, 20, 'days', 'SUNSET', 60, NULL, NULL, NULL, NULL, 5, 4, 'motregen', 'of 1 uur na', NULL, '2 x 2 uur', false, false, false, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-09-15', DATE '2000-10-15', true, NULL ),
  ( 2, DATE '2000-09-15', DATE '2000-10-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis nattereri') AND function_id = (SELECT id FROM functions WHERE name = 'Paarverblijf') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis emarginatus'), (SELECT id FROM functions WHERE name = 'Paarverblijf'), 2, 2, 20, 'days', 'ABSOLUTE_TIME', 0, '22:00:00', '01:00:00', NULL, NULL, 5, 4, 'motregen', NULL, NULL, '2 x 2 uur', false, false, false, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-08-15', DATE '2000-09-15', true, NULL ),
  ( 2, DATE '2000-08-15', DATE '2000-09-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis emarginatus') AND function_id = (SELECT id FROM functions WHERE name = 'Paarverblijf') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis dasycneme'), (SELECT id FROM functions WHERE name = 'Paarverblijf'), 2, 3, 20, 'days', 'SUNSET', NULL, NULL, NULL, 'SUNRISE', NULL, 5, 4, 'geen neerslag, geen mist boven watergangen', 'verplicht start zonsondergang bij avondonderzoek', 'verplicht tot zonsopgang bij ochtendonderzoek', '2 x 3 uur', false, false, false, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-08-15', DATE '2000-09-15', true, NULL ),
  ( 2, DATE '2000-08-15', DATE '2000-09-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis dasycneme') AND function_id = (SELECT id FROM functions WHERE name = 'Paarverblijf') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis daubentonii'), (SELECT id FROM functions WHERE name = 'Paarverblijf'), 2, 2, 20, 'days', 'ABSOLUTE_TIME', 0, '22:00:00', '01:00:00', NULL, NULL, 5, 4, 'motregen', NULL, NULL, '2 x 2 uur', false, false, false, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-08-15', DATE '2000-09-15', true, NULL ),
  ( 2, DATE '2000-08-15', DATE '2000-09-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis daubentonii') AND function_id = (SELECT id FROM functions WHERE name = 'Paarverblijf') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis myotis'), (SELECT id FROM functions WHERE name = 'Paarverblijf'), 2, 2, 20, 'days', 'ABSOLUTE_TIME', 0, '22:00:00', '01:00:00', NULL, NULL, 5, 4, 'motregen', NULL, NULL, '2 x 2 uur', false, false, false, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-08-15', DATE '2000-09-15', true, NULL ),
  ( 2, DATE '2000-08-15', DATE '2000-09-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis myotis') AND function_id = (SELECT id FROM functions WHERE name = 'Paarverblijf') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Pipistrellus nathusii'), (SELECT id FROM functions WHERE name = 'Vliegroute'), 2, 2, 8, 'weeks', 'SUNSET', 0, NULL, NULL, 'SUNRISE', 0, 10, 4, 'motregen', NULL, NULL, '2 x 2 uur, waarvan 1 x in de kraamperiode', false, false, false, true);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-04-15', DATE '2000-10-01', true, NULL ),
  ( 2, DATE '2000-04-15', DATE '2000-10-01', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Pipistrellus nathusii') AND function_id = (SELECT id FROM functions WHERE name = 'Vliegroute') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Pipistrellus pipistrellus'), (SELECT id FROM functions WHERE name = 'Vliegroute'), 2, 2, 8, 'weeks', 'SUNSET', 0, NULL, NULL, 'SUNRISE', 0, 10, 3, 'motregen', NULL, NULL, '2 x 2 uur, waarvan 1 x in de kraamperiode', false, false, false, true);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-04-15', DATE '2000-10-15', true, NULL ),
  ( 2, DATE '2000-04-15', DATE '2000-10-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Pipistrellus pipistrellus') AND function_id = (SELECT id FROM functions WHERE name = 'Vliegroute') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Pipistrellus pygmeus'), (SELECT id FROM functions WHERE name = 'Vliegroute'), 2, 2, 8, 'weeks', 'SUNSET', 0, NULL, NULL, 'SUNRISE', 0, 10, 3, 'motregen', NULL, NULL, '2 x 2 uur, waarvan 1 x in de kraamperiode', false, false, false, true);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-04-15', DATE '2000-10-15', true, NULL ),
  ( 2, DATE '2000-04-15', DATE '2000-10-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Pipistrellus pygmeus') AND function_id = (SELECT id FROM functions WHERE name = 'Vliegroute') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Plecotus auritus'), (SELECT id FROM functions WHERE name = 'Vliegroute'), 2, 2, 8, 'weeks', 'SUNSET', 30, NULL, NULL, 'SUNRISE', 60, 5, 2, 'geen regen', 'maximaal donker', NULL, '2 x 2 uur, waarvan 1 x in de kraamperiode', false, false, false, true);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-04-15', DATE '2000-10-01', true, NULL ),
  ( 2, DATE '2000-04-15', DATE '2000-10-01', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Plecotus auritus') AND function_id = (SELECT id FROM functions WHERE name = 'Vliegroute') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Plecotus austriacus'), (SELECT id FROM functions WHERE name = 'Vliegroute'), 2, 2, 8, 'weeks', 'SUNSET', 30, NULL, NULL, 'SUNRISE', 60, 5, 2, 'geen regen', 'maximaal donker', NULL, '2 x 2 uur, waarvan 1 x in de kraamperiode', false, false, false, true);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-04-15', DATE '2000-10-01', true, NULL ),
  ( 2, DATE '2000-04-15', DATE '2000-10-01', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Plecotus austriacus') AND function_id = (SELECT id FROM functions WHERE name = 'Vliegroute') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Vespertilio murinus'), (SELECT id FROM functions WHERE name = 'Vliegroute'), 2, 2, 8, 'weeks', 'SUNSET', 0, NULL, NULL, 'SUNRISE', 60, 10, 4, 'motregen', NULL, NULL, '2 x 2 uur, waarvan 1 x in de kraamperiode', false, false, false, true);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-04-15', DATE '2000-11-01', true, NULL ),
  ( 2, DATE '2000-04-15', DATE '2000-11-01', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Vespertilio murinus') AND function_id = (SELECT id FROM functions WHERE name = 'Vliegroute') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Eptesicus serotinus'), (SELECT id FROM functions WHERE name = 'Vliegroute'), 2, 2, 8, 'weeks', 'SUNSET', 0, NULL, NULL, NULL, NULL, 12, 4, 'motregen', NULL, NULL, '2 x 2 uur, waarvan 1 x in de kraamperiode', false, false, false, true);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-04-15', DATE '2000-10-01', true, NULL ),
  ( 2, DATE '2000-04-15', DATE '2000-10-01', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Eptesicus serotinus') AND function_id = (SELECT id FROM functions WHERE name = 'Vliegroute') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Nyctalus noctula'), (SELECT id FROM functions WHERE name = 'Vliegroute'), 2, 2, 8, 'weeks', 'SUNSET', 0, NULL, NULL, 'SUNRISE', 30, 12, 4, 'motregen', NULL, NULL, '2 x 2 uur, waarvan 1 x in de kraamperiode', false, false, false, true);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-04-15', DATE '2000-10-01', true, NULL ),
  ( 2, DATE '2000-04-15', DATE '2000-10-01', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Nyctalus noctula') AND function_id = (SELECT id FROM functions WHERE name = 'Vliegroute') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Nyctalus leisleri'), (SELECT id FROM functions WHERE name = 'Vliegroute'), 2, 2, 8, 'weeks', 'SUNSET', 0, NULL, NULL, 'SUNRISE', 30, NULL, NULL, NULL, NULL, NULL, '2 x 2 uur, waarvan 1 x in de kraamperiode', false, false, false, true);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-05-15', DATE '2000-08-15', true, NULL ),
  ( 2, DATE '2000-05-15', DATE '2000-08-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Nyctalus leisleri') AND function_id = (SELECT id FROM functions WHERE name = 'Vliegroute') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis mystacinus'), (SELECT id FROM functions WHERE name = 'Vliegroute'), 2, 2, 8, 'weeks', 'SUNSET', 15, NULL, NULL, 'SUNRISE', 60, 10, 4, 'motregen', NULL, NULL, '2 x 2 uur, waarvan 1x in de kraamperiode & eventueel 1 ochtend', true, false, false, true);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-05-15', DATE '2000-09-15', true, NULL ),
  ( 2, DATE '2000-05-15', DATE '2000-09-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis mystacinus') AND function_id = (SELECT id FROM functions WHERE name = 'Vliegroute') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis bechsteinii'), (SELECT id FROM functions WHERE name = 'Vliegroute'), 2, 2, 8, 'weeks', 'SUNSET', 15, NULL, NULL, 'SUNRISE', 60, 10, 4, 'motregen', NULL, NULL, '2 x 2 uur, waarvan 1x in de kraamperiode & eventueel 1 ochtend', true, false, false, true);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-05-15', DATE '2000-09-15', true, NULL ),
  ( 2, DATE '2000-05-15', DATE '2000-09-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis bechsteinii') AND function_id = (SELECT id FROM functions WHERE name = 'Vliegroute') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis brandtii'), (SELECT id FROM functions WHERE name = 'Vliegroute'), 2, 2, 8, 'weeks', 'SUNSET', 15, NULL, NULL, 'SUNRISE', 60, 10, 4, 'motregen', NULL, NULL, '2 x 2 uur, waarvan 1x in de kraamperiode & eventueel 1 ochtend', true, false, false, true);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-05-15', DATE '2000-09-15', true, NULL ),
  ( 2, DATE '2000-05-15', DATE '2000-09-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis brandtii') AND function_id = (SELECT id FROM functions WHERE name = 'Vliegroute') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis nattereri'), (SELECT id FROM functions WHERE name = 'Vliegroute'), 2, 2, 8, 'weeks', 'SUNSET', 15, NULL, NULL, 'SUNRISE', 60, 10, 4, 'motregen', NULL, NULL, '2 x 2 uur, waarvan 1x in de kraamperiode & eventueel 1 ochtend', true, false, false, true);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-05-15', DATE '2000-09-15', true, NULL ),
  ( 2, DATE '2000-05-15', DATE '2000-09-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis nattereri') AND function_id = (SELECT id FROM functions WHERE name = 'Vliegroute') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis emarginatus'), (SELECT id FROM functions WHERE name = 'Vliegroute'), 2, 2, 8, 'weeks', 'SUNSET', 15, NULL, NULL, 'SUNRISE', 60, 10, 4, 'motregen', NULL, NULL, '2 x 2 uur, waarvan 1x in de kraamperiode & eventueel 1 ochtend', true, false, false, true);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-05-15', DATE '2000-09-15', true, NULL ),
  ( 2, DATE '2000-05-15', DATE '2000-09-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis emarginatus') AND function_id = (SELECT id FROM functions WHERE name = 'Vliegroute') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis dasycneme'), (SELECT id FROM functions WHERE name = 'Vliegroute'), 2, 2, 6, 'weeks', 'SUNSET', 15, NULL, NULL, NULL, NULL, 8, 3, 'geen neerslag, geen mist boven watergangen', NULL, NULL, '2 x 2 uur, ''s avonds waarvan 1x in de kraamperiode en 1x buiten kraamperiode', false, true, false, true);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-05-15', DATE '2000-08-15', true, NULL ),
  ( 2, DATE '2000-05-15', DATE '2000-08-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis dasycneme') AND function_id = (SELECT id FROM functions WHERE name = 'Vliegroute') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis daubentonii'), (SELECT id FROM functions WHERE name = 'Vliegroute'), 2, 2, 8, 'weeks', 'SUNSET', 15, NULL, NULL, 'SUNRISE', 60, 10, 4, 'motregen', NULL, NULL, '2 x 2 uur, waarvan 1x in de kraamperiode & eventueel 1 ochtend', true, false, false, true);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-04-15', DATE '2000-09-15', true, NULL ),
  ( 2, DATE '2000-04-15', DATE '2000-09-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis daubentonii') AND function_id = (SELECT id FROM functions WHERE name = 'Vliegroute') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis myotis'), (SELECT id FROM functions WHERE name = 'Vliegroute'), 2, 2, 8, 'weeks', 'SUNSET', 15, NULL, NULL, 'SUNRISE', 60, 10, 4, 'motregen', NULL, NULL, '2 x 2 uur, waarvan 1x in de kraamperiode & eventueel 1 ochtend', true, false, false, true);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-05-15', DATE '2000-09-15', true, NULL ),
  ( 2, DATE '2000-05-15', DATE '2000-09-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis myotis') AND function_id = (SELECT id FROM functions WHERE name = 'Vliegroute') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Pipistrellus nathusii'), (SELECT id FROM functions WHERE name = 'Migratieroute'), NULL, NULL, 5, 'days', 'FULL_NIGHT', NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'Omstandigheden noteren', NULL, NULL, '1 x per week in de periode', false, false, false, false);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis dasycneme'), (SELECT id FROM functions WHERE name = 'Migratieroute'), NULL, NULL, NULL, NULL, 'FULL_NIGHT', NULL, NULL, NULL, NULL, NULL, NULL, '3', 'Omstandigheden noteren', NULL, NULL, '6 weken in de periode 15 feb-1 mei OF 3 weken in de periode 1 aug-1 okt', false, false, false, false);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Pipistrellus nathusii'), (SELECT id FROM functions WHERE name = 'Foerageergebied'), 2, 2, 8, 'weeks', 'SUNSET', 0, NULL, NULL, 'SUNRISE', 0, 10, 4, 'motregen', NULL, NULL, '2 x 2 uur, waarvan 1 x in de periode 1 aug - 1 okt', false, false, false, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-04-15', DATE '2000-10-01', true, NULL ),
  ( 2, DATE '2000-04-15', DATE '2000-10-01', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Pipistrellus nathusii') AND function_id = (SELECT id FROM functions WHERE name = 'Foerageergebied') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Pipistrellus pipistrellus'), (SELECT id FROM functions WHERE name = 'Foerageergebied'), 2, 2, 8, 'weeks', 'SUNSET', 0, NULL, NULL, 'SUNRISE', 0, 10, 3, 'motregen', NULL, NULL, '2 x 2 uur, waarvan 1 x in de kraamperiode', false, false, false, true);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-04-15', DATE '2000-10-15', true, NULL ),
  ( 2, DATE '2000-04-15', DATE '2000-10-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Pipistrellus pipistrellus') AND function_id = (SELECT id FROM functions WHERE name = 'Foerageergebied') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Pipistrellus pygmeus'), (SELECT id FROM functions WHERE name = 'Foerageergebied'), 2, 2, 8, 'weeks', 'SUNSET', 0, NULL, NULL, 'SUNRISE', 0, 10, 3, 'motregen', NULL, NULL, '2 x 2 uur, waarvan 1 x in de kraamperiode', false, false, false, true);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-04-15', DATE '2000-10-15', true, NULL ),
  ( 2, DATE '2000-04-15', DATE '2000-10-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Pipistrellus pygmeus') AND function_id = (SELECT id FROM functions WHERE name = 'Foerageergebied') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Plecotus auritus'), (SELECT id FROM functions WHERE name = 'Foerageergebied'), 2, 2, 8, 'weeks', 'SUNSET', 30, NULL, NULL, 'SUNRISE', 60, 5, 2, 'geen regen', 'maximaal donker', NULL, '2 x 2 uur, waarvan 1 x in de kraamperiode', false, false, false, true);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-04-15', DATE '2000-10-01', true, NULL ),
  ( 2, DATE '2000-04-15', DATE '2000-10-01', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Plecotus auritus') AND function_id = (SELECT id FROM functions WHERE name = 'Foerageergebied') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Plecotus austriacus'), (SELECT id FROM functions WHERE name = 'Foerageergebied'), 2, 2, 8, 'weeks', 'SUNSET', 30, NULL, NULL, 'SUNRISE', 60, 5, 2, 'geen regen', 'maximaal donker', NULL, '2 x 2 uur, waarvan 1 x in de kraamperiode', false, false, false, true);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-04-15', DATE '2000-10-01', true, NULL ),
  ( 2, DATE '2000-04-15', DATE '2000-10-01', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Plecotus austriacus') AND function_id = (SELECT id FROM functions WHERE name = 'Foerageergebied') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Vespertilio murinus'), (SELECT id FROM functions WHERE name = 'Foerageergebied'), 2, 2, 8, 'weeks', 'SUNSET', 0, NULL, NULL, 'SUNRISE', 60, 10, 4, 'motregen', NULL, NULL, '2 x 2 uur, waarvan 1 x in de kraamperiode', false, false, false, true);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-04-15', DATE '2000-11-01', true, NULL ),
  ( 2, DATE '2000-04-15', DATE '2000-11-01', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Vespertilio murinus') AND function_id = (SELECT id FROM functions WHERE name = 'Foerageergebied') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Eptesicus serotinus'), (SELECT id FROM functions WHERE name = 'Foerageergebied'), 2, 2, 8, 'weeks', 'SUNSET', 0, NULL, NULL, NULL, NULL, 12, 4, 'motregen', NULL, NULL, '2 x 2 uur, waarvan 1 x in de kraamperiode', false, false, false, true);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-04-15', DATE '2000-10-01', true, NULL ),
  ( 2, DATE '2000-04-15', DATE '2000-10-01', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Eptesicus serotinus') AND function_id = (SELECT id FROM functions WHERE name = 'Foerageergebied') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Nyctalus noctula'), (SELECT id FROM functions WHERE name = 'Foerageergebied'), 2, 2, 8, 'weeks', 'SUNSET', 0, NULL, NULL, 'SUNRISE', 30, 12, 4, 'motregen', NULL, NULL, '2 x 2 uur, waarvan 1 x in de kraamperiode', false, false, false, true);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-04-15', DATE '2000-10-01', true, NULL ),
  ( 2, DATE '2000-04-15', DATE '2000-10-01', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Nyctalus noctula') AND function_id = (SELECT id FROM functions WHERE name = 'Foerageergebied') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Nyctalus leisleri'), (SELECT id FROM functions WHERE name = 'Foerageergebied'), 2, 2, 8, 'weeks', 'SUNSET', 0, NULL, NULL, 'SUNRISE', 30, NULL, NULL, NULL, NULL, NULL, '2 x 2 uur, waarvan 1 x in de kraamperiode', false, false, false, true);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-05-15', DATE '2000-08-15', true, NULL ),
  ( 2, DATE '2000-05-15', DATE '2000-08-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Nyctalus leisleri') AND function_id = (SELECT id FROM functions WHERE name = 'Foerageergebied') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis mystacinus'), (SELECT id FROM functions WHERE name = 'Foerageergebied'), 2, 2, 8, 'weeks', 'SUNSET', 15, NULL, NULL, 'SUNRISE', 60, 10, 4, 'motregen', NULL, NULL, '2 x 2 uur, waarvan 1x in de kraamperiode & eventueel 1 ochtend', true, false, false, true);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-05-15', DATE '2000-09-15', true, NULL ),
  ( 2, DATE '2000-05-15', DATE '2000-09-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis mystacinus') AND function_id = (SELECT id FROM functions WHERE name = 'Foerageergebied') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis bechsteinii'), (SELECT id FROM functions WHERE name = 'Foerageergebied'), 2, 2, 8, 'weeks', 'SUNSET', 15, NULL, NULL, 'SUNRISE', 60, 10, 4, 'motregen', NULL, NULL, '2 x 2 uur, waarvan 1x in de kraamperiode & eventueel 1 ochtend', true, false, false, true);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-05-15', DATE '2000-09-15', true, NULL ),
  ( 2, DATE '2000-05-15', DATE '2000-09-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis bechsteinii') AND function_id = (SELECT id FROM functions WHERE name = 'Foerageergebied') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis brandtii'), (SELECT id FROM functions WHERE name = 'Foerageergebied'), 2, 2, 8, 'weeks', 'SUNSET', 15, NULL, NULL, 'SUNRISE', 60, 10, 4, 'motregen', NULL, NULL, '2 x 2 uur, waarvan 1x in de kraamperiode & eventueel 1 ochtend', true, false, false, true);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-05-15', DATE '2000-09-15', true, NULL ),
  ( 2, DATE '2000-05-15', DATE '2000-09-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis brandtii') AND function_id = (SELECT id FROM functions WHERE name = 'Foerageergebied') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis nattereri'), (SELECT id FROM functions WHERE name = 'Foerageergebied'), 2, 2, 8, 'weeks', 'SUNSET', 15, NULL, NULL, 'SUNRISE', 60, 10, 4, 'motregen', NULL, NULL, '2 x 2 uur, waarvan 1x in de kraamperiode & eventueel 1 ochtend', true, false, false, true);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-05-15', DATE '2000-09-15', true, NULL ),
  ( 2, DATE '2000-05-15', DATE '2000-09-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis nattereri') AND function_id = (SELECT id FROM functions WHERE name = 'Foerageergebied') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis emarginatus'), (SELECT id FROM functions WHERE name = 'Foerageergebied'), 2, 2, 8, 'weeks', 'SUNSET', 15, NULL, NULL, 'SUNRISE', 60, 10, 4, 'motregen', NULL, NULL, '2 x 2 uur, waarvan 1x in de kraamperiode & eventueel 1 ochtend', true, false, false, true);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-05-15', DATE '2000-09-15', true, NULL ),
  ( 2, DATE '2000-05-15', DATE '2000-09-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis emarginatus') AND function_id = (SELECT id FROM functions WHERE name = 'Foerageergebied') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis dasycneme'), (SELECT id FROM functions WHERE name = 'Foerageergebied'), 2, 2, 6, 'weeks', 'SUNSET', 15, NULL, NULL, 'SUNRISE', 60, 8, 3, 'geen neerslag, geen mist boven watergangen', NULL, NULL, '2 x 2 uur, waarvan 1x in de kraamperiode & eventueel 1 ochtend', true, false, false, true);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-04-01', DATE '2000-08-15', true, NULL ),
  ( 2, DATE '2000-04-01', DATE '2000-08-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis dasycneme') AND function_id = (SELECT id FROM functions WHERE name = 'Foerageergebied') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis daubentonii'), (SELECT id FROM functions WHERE name = 'Foerageergebied'), 2, 2, 8, 'weeks', 'SUNSET', 15, NULL, NULL, 'SUNRISE', 60, 10, 4, 'motregen', NULL, NULL, '2 x 2 uur, waarvan 1x in de kraamperiode & eventueel 1 ochtend', true, false, false, true);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-04-15', DATE '2000-09-15', true, NULL ),
  ( 2, DATE '2000-04-15', DATE '2000-09-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis daubentonii') AND function_id = (SELECT id FROM functions WHERE name = 'Foerageergebied') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis myotis'), (SELECT id FROM functions WHERE name = 'Foerageergebied'), 2, 2, 8, 'weeks', 'SUNSET', 15, NULL, NULL, 'SUNRISE', 60, 10, 4, 'motregen', NULL, NULL, '2 x 2 uur, waarvan 1x in de kraamperiode & eventueel 1 ochtend', true, false, false, true);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  ( 1, DATE '2000-05-15', DATE '2000-09-15', true, NULL ),
  ( 2, DATE '2000-05-15', DATE '2000-09-15', true, NULL )
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name_latin = 'Myotis myotis') AND function_id = (SELECT id FROM functions WHERE name = 'Foerageergebied') ORDER BY id DESC LIMIT 1) AS p(id);
