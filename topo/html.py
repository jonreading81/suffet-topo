"""Standalone offline HTML map builder.

Embeds Leaflet, IGN tiles (base64), boulder photos (base64), and route data
into a single .html file that works without signal.
"""
import json
import os

from .style import ASSETS, ZOOM_MAX, ZOOM_MIN


# Placeholders replaced at build time:
#   __CSS__ __JS__ __TILES__ __DATA__ __LOGO__ __TB__ __CB__ __ZMIN__ __ZMAX__
_HTML = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<title>Refuge du Suffet boulders</title>
<style>__CSS__</style>
<style>
*{box-sizing:border-box} html,body{margin:0;height:100%;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;color:#1d1d1b}
#app{position:fixed;inset:0;display:flex;flex-direction:column}
#topbar{background:#004AAD;color:#fff;padding:10px 14px;z-index:1200;flex:0 0 auto;display:flex;align-items:center;justify-content:space-between;gap:12px}
#topbar .tt h1{margin:0;font-size:17px;font-weight:700;font-family:Georgia,"Times New Roman",serif}
#topbar .tt p{margin:2px 0 0;font-size:11.5px;color:#cfe0ea}
#topbar .logo svg{height:34px;width:auto;display:block}
#map{flex:1 1 auto;background:#e8edf4;z-index:1}
.pin{display:flex;align-items:center;justify-content:center;width:30px;height:30px;border-radius:50%;background:#004AAD;color:#fff;font-weight:700;font-size:13px;border:2.5px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.4)}
.pin.sel{background:#E4572E;transform:scale(1.12)}
.ref{display:flex;align-items:center;justify-content:center;width:30px;height:30px;border-radius:6px;background:#6AB0AB;color:#fff;border:2.5px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.4);font-size:16px}
#sheet{position:absolute;left:0;right:0;bottom:0;background:#fff;z-index:1100;border-top-left-radius:16px;border-top-right-radius:16px;box-shadow:0 -4px 20px rgba(0,0,0,.18);transform:translateY(102%);transition:transform .28s ease;max-height:64%;overflow-y:auto;padding:0 16px 20px}
#sheet.open{transform:translateY(0)}
.grab{width:38px;height:4px;background:#c8d2e0;border-radius:2px;margin:8px auto 4px}
.sheethd{display:flex;align-items:baseline;justify-content:space-between;gap:8px;padding:4px 0 6px;position:sticky;top:0;background:#fff}
.sheethd h2{margin:0;font-size:18px;font-weight:700;font-family:Georgia,serif;color:#004AAD}
.close{border:none;background:#eef2f8;border-radius:8px;font-size:18px;line-height:1;padding:6px 10px;cursor:pointer}
.metarow{display:flex;flex-wrap:wrap;gap:6px;margin:2px 0 10px}
.chip{font-size:11px;background:#e7eef7;color:#33506e;border-radius:6px;padding:3px 8px}
.chip.warn{background:#FAEEDA;color:#8a5a12;font-weight:600}
.photo{width:100%;border-radius:10px;border:.5px solid #dbe1ec;margin-bottom:10px}
.nophoto{width:100%;aspect-ratio:4/3;border-radius:10px;border:1px dashed #c3ccdb;display:flex;align-items:center;justify-content:center;color:#98a1b3;font-size:13px;margin-bottom:10px;background:#f7f9fc}
.prob{border-top:.5px solid #eaeef4;padding:9px 0}.prob:first-of-type{border-top:none}
.probhd{display:flex;align-items:center;gap:8px}
.dot{width:20px;height:20px;border-radius:50%;color:#fff;font-size:11px;font-weight:700;display:flex;align-items:center;justify-content:center;flex:0 0 auto}
.dot.proj{background:#fff!important;border:2px solid #A096EF;color:#A096EF}
.pname{font-weight:600;font-size:14px}
.pgrade{margin-left:auto;font-weight:700;color:#004AAD;font-size:14px}
.pgrade.proj{color:#A096EF}
.pbeta{font-size:12.5px;color:#555;margin:3px 0 0 28px;line-height:1.45}
.legend{font-size:11px;color:#8890a0;font-style:italic;margin-top:8px}
#hint{position:absolute;top:10px;left:50%;transform:translateX(-50%);z-index:1000;background:rgba(255,255,255,.92);border-radius:20px;padding:6px 14px;font-size:12px;color:#33506e;box-shadow:0 1px 6px rgba(0,0,0,.15)}
.leaflet-control-attribution{font-size:9px}
</style></head><body><div id="app">
<div id="topbar"><div class="tt"><h1>Refuge du Suffet boulders</h1><p>Haute-Maurienne · tap a marker · works offline</p></div><div class="logo">__LOGO__</div></div>
<div id="map"><div id="hint">Tap a boulder for problems + beta</div></div></div>
<div id="sheet"><div class="grab"></div><div id="sheetbody"></div></div>
<script>__JS__</script>
<script>
var TILES=__TILES__, DATA=__DATA__, EMPTY="data:image/gif;base64,R0lGODlhAQABAAAAACwAAAAAAQABAAA=";
var Off=L.TileLayer.extend({getTileUrl:function(c){return TILES[this.options.k+"/"+c.z+"/"+c.x+"/"+c.y]||EMPTY;}});
var tileBounds=L.latLngBounds(__TB__), contentBounds=L.latLngBounds(__CB__);
var map=L.map('map',{minZoom:__ZMIN__,maxZoom:__ZMAX__,maxBounds:tileBounds,maxBoundsViscosity:1.0,zoomControl:true});
var aerial=new Off('',{k:'aerial',minZoom:__ZMIN__,maxZoom:__ZMAX__,bounds:tileBounds,attribution:'© IGN / Géoplateforme'});
var topo=new Off('',{k:'topo',minZoom:__ZMIN__,maxZoom:__ZMAX__,bounds:tileBounds,attribution:'© IGN / Géoplateforme'});
aerial.addTo(map); L.control.layers({'Aerial':aerial,'Topo':topo},null,{collapsed:false}).addTo(map);
map.fitBounds(contentBounds);
var s=DATA.suffet;
L.marker([s.lat,s.lon],{icon:L.divIcon({className:'',html:'<div class="ref">⌂</div>',iconSize:[30,30],iconAnchor:[15,15]})}).addTo(map).bindTooltip(s.name+' · '+s.alt+' m',{direction:'right',offset:[14,0]});
DATA.boulders.forEach(function(b){
 var m=L.marker([b.lat,b.lon],{icon:L.divIcon({className:'',html:'<div class="pin" id="pin'+b.id+'">'+b.id+'</div>',iconSize:[30,30],iconAnchor:[15,15]})}).addTo(map);
 m.bindTooltip(b.name,{direction:'right',offset:[14,0]}); m.on('click',function(){openB(b);});});
var sheet=document.getElementById('sheet'),body=document.getElementById('sheetbody');
function openB(b){
 document.querySelectorAll('.pin').forEach(function(p){p.classList.remove('sel')});
 var pe=document.getElementById('pin'+b.id); if(pe)pe.classList.add('sel');
 var acc=(b.acc!=null&&b.acc>=15)?'<span class="chip warn">⚠ GPS ±'+b.acc+' m</span>':(b.acc!=null?'<span class="chip">GPS ±'+b.acc+' m</span>':'');
 var h='<div class="sheethd"><h2>'+b.name+'</h2><button class="close" onclick="closeSheet()">×</button></div>';
 h+='<div class="metarow"><span class="chip">'+b.lat.toFixed(5)+'°N, '+b.lon.toFixed(5)+'°E</span>'+(b.alt?'<span class="chip">'+b.alt+' m</span>':'')+'<span class="chip">bearing '+b.bearing+'</span>'+acc+'</div>';
 h+=b.photo?('<img class="photo" src="'+b.photo+'">'):'<div class="nophoto">photo added from your upload</div>';
 var hasP=false;
 b.problems.forEach(function(p){var pr=p.project;if(pr)hasP=true;
   h+='<div class="prob"><div class="probhd"><div class="dot'+(pr?' proj':'')+'" style="'+(pr?'':'background:'+p.color)+'">'+p.n+'</div><span class="pname">'+p.name+'</span><span class="pgrade'+(pr?' proj':'')+'">'+p.grade+'</span></div><div class="pbeta">'+p.beta+'</div></div>';});
 if(hasP) h+='<div class="legend">Dashed line + open marker = project (unclimbed).</div>';
 body.innerHTML=h; sheet.classList.add('open'); map.panTo([b.lat,b.lon]);
}
function closeSheet(){sheet.classList.remove('open');document.querySelectorAll('.pin').forEach(function(p){p.classList.remove('sel')});}
map.on('click',closeSheet);
</script></body></html>"""


def build_html(boulders, refuge, tiles, bbox, out_path):
    css = open(os.path.join(ASSETS, "vendor", "leaflet.css")).read()
    js = open(os.path.join(ASSETS, "vendor", "leaflet.js")).read()
    logo = open(os.path.join(ASSETS, "logo_white.svg")).read()
    data = {"suffet": refuge, "boulders": []}
    for b in boulders:
        data["boulders"].append(
            {
                "id": b["id"],
                "name": b["name"],
                "lat": b["lat"],
                "lon": b["lon"],
                "alt": b.get("alt"),
                "acc": b.get("acc"),
                "bearing": b.get("bearing_str", "–"),
                "photo": b["_photo_uri"],
                "problems": [
                    {
                        "n": p["no"],
                        "name": p["name"],
                        "grade": p["grade"],
                        "color": p["color"],
                        "project": p["project"],
                        "beta": p["notes"],
                    }
                    for p in b["problems"]
                ],
            }
        )
    DATA = json.dumps(data)
    latmin, lonmin, latmax, lonmax = bbox
    # content bounds = tight around points
    pts = [(refuge["lat"], refuge["lon"])] + [(b["lat"], b["lon"]) for b in boulders]
    clatmin = min(p[0] for p in pts) - 0.0005
    clatmax = max(p[0] for p in pts) + 0.0005
    clonmin = min(p[1] for p in pts) - 0.0008
    clonmax = max(p[1] for p in pts) + 0.0008

    html = (
        _HTML.replace("__CSS__", css)
        .replace("__JS__", js)
        .replace("__TILES__", json.dumps(tiles))
        .replace("__DATA__", DATA)
        .replace("__LOGO__", logo)
        .replace("__TB__", f"[[{latmin},{lonmin}],[{latmax},{lonmax}]]")
        .replace("__CB__", f"[[{clatmin},{clonmin}],[{clatmax},{clonmax}]]")
        .replace("__ZMIN__", str(ZOOM_MIN))
        .replace("__ZMAX__", str(ZOOM_MAX))
    )
    open(out_path, "w").write(html)
