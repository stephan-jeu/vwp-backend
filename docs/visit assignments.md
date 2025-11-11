I want to start working on a planning visit module. Planning visits means assigning 1 or more researchers. This will consist of two important parts:
1) Selecting the visits that should be done
2) Selecting the researchers that should do the visit.
3) Ordering the researchers if multiple are available for a visit

# 1 Selecting Visits
All three parts are a bit complicated. So I want to start with selecting the visits. We will be assigning visits per week.
Only visits are eligible to be assigned that follow these criteria:
1 - have a start date =< the friday of the selected week and an end date that is >= start of selected week (monday)
2 - the number of visits should not exceed the total available days per week (all researchers combined) for each day part minus some spare capacity: -2 for Avond, -1 for Ochtend and -2 voor Dag
3 - All the flex capacity can be assigned to any visit taking in order of priority. I'll describe the rules for setting priorities below.
4 - A visit has required_researchers. Capacity calculations should take that into account, so we should deduce visit * required_researchers for that visit from the remaining capacity 
5 - A complication arises when visit start_date or visit end_date fall in the selected week. Keep in mind that a researcher can only do 1 visit per day (either morning, daytime or evening). So if for example multiple visits have a start date that is on a friday (last day of the week), that means we cannot exceed the number of researchers with capacity for that part of day, if it falls on a thursday we should make sure the number of assigned visits don't exceed 2 * the number of researchers available for that time slot. The same principle applies to end date, but then we should calculate from the beginning of the week: monday, no more than the number of researchers for that time slot, tuesday, 2 times the number of researchers. What may help is that start date are always either the 1st or the 15th and end dates the 15th or the end of the month.
6 - Visits should be assigned in the following order of priority (respecting the criteria above):
- Visits with priority = true
- Visits with an end date that =< than 14 days from the beginning of the selected week
- Visits where family priority =< 3. Visits are always per families with the same priority also if there are multiple species, so we can take the first species linked to this visit to determine the family.
- Visits that have a function name that starts with SMP. Here again you can be sure that if the first function associated with the visit starts with SMP the others will as well
- Visits where function name contains Vliegroute or Foerageergebied
- Visits where HUB is true
- Visits where Sleutel is true
- Visits where Fiets, DVP or WBC is true
- All other visits that qualify

# 2 Selecting researchers
Researchers can only be assigned if they qualify. That means we should match their user qualifications with the conditions of the visit
1 - Researchers should qualify for all the families of the species of the visit. The matching visit family -> user property is as follows:
Biggenkruid -> biggenkruid
Langoren -> langoor
Pad -> pad
Roofvogel -> roofvogel
Schijfhoren -> schijfhoren
Vleermuis -> vleermuis
Vlinder -> vlinder
Zangvogel -> zangvogel
Zwaluw -> zwaluw

2 - If first Visit function name starts with SMP user smp must be true

3 - If any vistit function name is 'Vliegroute' and/or 'Foerageergebied' user vrfg must be true

4 - The following visit booleans must also match with the user: hub, fiets, wbc dvp, sleutel (same field naming between user and visit)

# 3 Ordering researchers
A lot of times we'll have multiple researchers available for a visit. In that case the following criteria should be used to order the researchers:
1- Travel time: using google maps api we should calculate the travel time from the researcher's current location to the visit location and set a 'travel' value incrementing for eache subsequent 15 minutes. So travel time 0-15 minutes is 1, 15-30 2, 30-45 3, 45-60 4, 60-75 6 and higher is excluded. We should normalize the value by dividing by 6 (all values should be between 0 and 1)
2- already assigned: number of already assigned visits / total available capacity
3 - number of assigned visits where number of researchers > 2 / total number of planned visits where number of researchers > 2
4 - number of visits that require fiets / total number of visits that require fiets
5 - number of already assigned visits for this researcher to this project / by total number of visits for this project

Each criteria has different weights. The weights are as follows:
1 - travel time: 4
2 - already assigned: 32
3 - number of assigned visits where number of researchers > 2 / total number of planned visits where number of researchers > 2: 3
4 - number of visits that require fiets / total number of visits that require fiets: 1
5 - number of already assigned visits for this researcher to this project / by total number of visits for this project: 1

The values should be multiplied by the weights and then added up to get a final score. The researcher(s) with the lowest score should be assigned the visit.


