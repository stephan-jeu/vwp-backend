I want to create a new admin only screen: Cluster SFC. Where SFC stands for Soort Functie Combinatie.
This page has two goals:

- Adding clusters to a project, this is a relatively straightforward create, update or delete
- Based on the selected functions and species, create visits for this cluster.

The screen should be as follows. Below the title (Cluster SFC) there are four inputs:

- A select field with searchable project code, which will be the project to which this cluster should be linked. If you select a project, it displays all the clusters for this project in the table below
- An 'Adres' (address column) field
- Cluster number
- Functions multi select field
- Species multi select fielda

A Toevoegen knop that:

- creates the cluster entry in the backend and adds it to the table
- generates visits for the selected functions and species (The logic for doing this is a bit complex, I'll explain below)
- resets the Cluster number field

Then there is the Cluster table. This is a grouped table (see nuxt uit https://ui.nuxt.com/docs/components/table#with-grouped-rows) where visits are grouped by cluster number. On the grouped row also display the address and the number of visits (aggregationFn) and address. The end of the row has a DropdownMenu with the following actions

- Dupliceer that shows a modal asking for the cluster number and address (with current value of address) and then duplicates all the visit records to the new cluster.
- Delete (displays modal asking Weet je zeker dat je dit cluster en alle bezoeken wilt verwijderen)
  The expanded section displays a list of inputs for all the visits linked to this cluster. The inputs are:
  Functies (multiselect), Soorten (multiselect), Aantal onderzoekers (InputNumber default 1), Bezoek nummer, Periode, Tijd start, Duur, Weereisen, expertise_niveau, wbc, fiets, hub, dvp, aantal onderzoekers, opmerkingen planning, opmerkingen veld

When adding visits via Toevoegen knop, the visits have to be added in a particular way. The general rule is that based on the selected species and functions, we should select the corresponding protocols (and corresponding protocol_visit_windows) and create the visits with the values of these protocols. The number of visits to be created should come from visits field in protocols The visit fields that should come from the protocols are:
the from_date and to_date based on protocol_visit_window and the index of the visit (if it's the first, second, etc visit in the sequence of required visits)
duration
min_temperature_celsius
max_wind_force_bft
max_precipitation
remarks_field (visit_conditions_text from protocol)

Other fields that should be automatically filled are:
group_id (a random string used to identify this series of visits)
visit_nr: this is a sequential number of all the visits for this particular cluster (so not necessarily for the visits we're creating here)

This was the general rule, however there is a complication. A user can select multiple functions and species. In a lot of cases visits of different functions and species should be combined.
When species are part of the following families, they can be combined into one visit window sequence if the visit period overlaps between the protocols and if the protocol time corresponds, for example evening (after sunset) or morning (before sunrise). The families that could be combined are:
Vleermuis en Zwaluw (with some particular rules I'll describe below)
Zangvogel
Roofvogel
Vlinder
Leporidae

An important principle is that the most restrictive conditions should be applied to the grouped species and functions. That means for example if the protocol for function A and species B has a visit window for the first visit from 1 april until 1 june and function A for species C has a visit window from 15 april to 1 july, the grouped visit should take place between 15 april and 1 june. The same choose the strictest condition principle applies to the weather (e.g. minimum temperature is 5, 7 and 10 you should choose 10), the time (between start at sunrise or start 2 hours after sunrise, choose start time sunrise), duration and minimum time between visits.

For Vleermuis the allowed combinations are more restrictive. So you only combine visits in following cases:

- function name is 'kraamverblijfplaats' and name = 'zomerverblijfplaats'. Since the period for zomerverblijfplaats is much longer you have to plan the two visits in the period of kraamverblijfplaats (following the principle of the most restrictive conditions).
- function name is 'paarverblijf' except for where species.abbreviation name equals 'BoV' or 'BrV' or 'TV'
- function names are 'paarverblijf' and 'massawinterverblijfplaats'. This is a more complicated case since here we should only combine the second visit of the three. So you start with massawinterverblijf then at least 10 days later you do both massawinterverblijf and paarverbljf and then later you do the third visit which is paarverblijf only
- the most complicated combination resembles this previous somewhat. It is in case you have the combination zomerverblijf and kraamverblijfplaats and Nest as functionname and you also have Gierzwaluw as species.name (family Zwaluw) together with Vleermuis species. The Gierzwaluw requires 3 visits while the bats require 2 visits. So the first visit (between 1 and 15 june), should be both Vleermuis and Gierzwaluw, the second visit (between 15 and 30 june) should be only Gierzwaluw and the third visit (between 1 july and 15 july) should be both Vleermuis and Gierzwaluw again.
