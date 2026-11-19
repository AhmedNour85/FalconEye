# Arcade for the ArcGIS Strategic Dashboard

Data expressions for the dashboard item "CityView Strategic Dashboard". Paste each one into
*Data expressions* in the ArcGIS Dashboards editor. Each returns a FeatureSet, which is what dashboards need.

Incidents layer item: `1514541f9358445ba3269ef20a83c381` (layer 0). Dates in this layer are ISO text (`2026-10-26T01:31:01Z`).

## 1. KPIs (one row: open, critical_open, resolved, avg_hours_to_resolve)

```arcade
var fs = FeatureSetByPortalItem(Portal('https://esrisaudi-ai.maps.arcgis.com'), '1514541f9358445ba3269ef20a83c381', 0,
  ['Status', 'Severity', 'Created_Date', 'Last_Updated'], false)
var open = 0, crit = 0, res = 0, hrs = 0
for (var f in fs) {
  if (f.Status == 'Resolved') { res += 1; hrs += DateDiff(Date(f.Last_Updated), Date(f.Created_Date), 'hours') }
  else if (f.Status != 'Closed - False Positive') { open += 1; if (f.Severity == 'Critical') { crit += 1 } }
}
return FeatureSet(Text({ fields: [
    { name: 'open', type: 'esriFieldTypeInteger' }, { name: 'critical_open', type: 'esriFieldTypeInteger' },
    { name: 'resolved', type: 'esriFieldTypeInteger' }, { name: 'avg_hours', type: 'esriFieldTypeDouble' }],
  geometryType: '', features: [{ attributes: { open: open, critical_open: crit, resolved: res, avg_hours: IIf(res > 0, Round(hrs / res, 1), 0) } }] }))
```

## 2. Incidents per day, last 45 days (feeds a serial chart)

```arcade
var fs = FeatureSetByPortalItem(Portal('https://esrisaudi-ai.maps.arcgis.com'), '1514541f9358445ba3269ef20a83c381', 0, ['Created_Date'], false)
var counts = {}
var start = DateAdd(Now(), -45, 'days')
for (var f in fs) {
  var d = Date(f.Created_Date)
  if (d >= start) { var k = Text(d, 'YYYY-MM-DD'); counts[k] = IIf(HasKey(counts, k), counts[k] + 1, 1) }
}
var rows = []
for (var i = 44; i >= 0; i--) {
  var k = Text(DateAdd(Now(), -i, 'days'), 'YYYY-MM-DD')
  Push(rows, { attributes: { day: k, incidents: IIf(HasKey(counts, k), counts[k], 0) } })
}
return FeatureSet(Text({ fields: [{ name: 'day', type: 'esriFieldTypeString' }, { name: 'incidents', type: 'esriFieldTypeInteger' }],
  geometryType: '', features: rows }))
```

## 3. List: advanced formatting (incidents list)

```arcade
var dot = Decode($feature.Severity, 'Critical', '🔴', 'High', '🟠', 'Medium', '🟡', '🟢')
return { textColor: '', backgroundColor: '', separatorColor: '', selectionColor: '', selectionTextColor: '', attributes: {} ,
  text: dot + ' ' + $feature.Incident_Type + ' · ' + $feature.Area_Name + '\n' + $feature.Status }
```
