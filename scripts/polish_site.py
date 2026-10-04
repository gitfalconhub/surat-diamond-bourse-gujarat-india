# SPDX-License-Identifier: GPL-3.0-or-later
"""Editable reference-informed landscape/site pass. Coordinates and sizes are metres.

Call ``apply(scene)`` on the existing scene, never on a blank scene. The module
only rebuilds its own collection and hides explicitly named legacy entourage.
It uses shared mesh data for all plants and furniture; no external assets.
"""
from __future__ import annotations

import json
import math
import random
import bpy
from mathutils import Vector
from sdb_utils import MeshBatch, material, polygon_prism, shaped_wall, point_at

COLLECTION = "Polish | Landscape and site"
PREFIX = "Polish Site | "
COURTS = [(-87, 63, 12, 33), (-27, 63, 12, 33), (35, 63, 10, 32),
          (-113, -53, 12, 32), (-53, -53, 12, 32), (9, -53, 11, 31), (80, -53, 11, 29)]
PARKING_EXCLUSION = (-210, -170, -115, -55)


class Geometry:
    """Compact editable multi-material mesh, avoiding thousands of operators."""
    def __init__(self):
        self.verts, self.faces, self.mats = [], [], []

    def face(self, points, mat=0):
        base = len(self.verts)
        self.verts.extend(tuple(p) for p in points)
        self.faces.append(tuple(range(base, base + len(points))))
        self.mats.append(mat)

    def box(self, a, b, mat=0):
        x, y, z = a; X, Y, Z = b
        base = len(self.verts)
        self.verts.extend([(x,y,z),(X,y,z),(X,Y,z),(x,Y,z),(x,y,Z),(X,y,Z),(X,Y,Z),(x,Y,Z)])
        for ids in [(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]:
            self.faces.append(tuple(base+i for i in ids)); self.mats.append(mat)

    def tube(self, start, end, r1, r2=None, mat=0, sides=8):
        a, b = Vector(start), Vector(end)
        axis = b-a
        if axis.length < .00001: return
        axis.normalize()
        u = axis.cross(Vector((0,0,1)))
        if u.length < .01: u = Vector((1,0,0))
        u.normalize(); v = axis.cross(u)
        base = len(self.verts)
        for point, radius in [(a,r1),(b,r1 if r2 is None else r2)]:
            for i in range(sides):
                t = i*2*math.pi/sides
                self.verts.append(tuple(point + (u*math.cos(t)+v*math.sin(t))*radius))
        self.faces.extend([tuple(base+i for i in reversed(range(sides))),tuple(base+sides+i for i in range(sides))])
        self.mats.extend([mat,mat])
        for i in range(sides):
            j=(i+1)%sides
            self.faces.append((base+i,base+j,base+sides+j,base+sides+i));self.mats.append(mat)

    def ellipsoid(self, center, radii, mat=0, segments=16, rings=9):
        base = len(self.verts)
        for j in range(rings+1):
            t=math.pi*j/rings
            for i in range(segments):
                a=math.pi*2*i/segments
                self.verts.append((center[0]+radii[0]*math.sin(t)*math.cos(a),
                                   center[1]+radii[1]*math.sin(t)*math.sin(a),center[2]+radii[2]*math.cos(t)))
        for j in range(rings):
            for i in range(segments):
                a=base+j*segments+i;b=base+j*segments+(i+1)%segments
                self.faces.append((a,b,b+segments,a+segments));self.mats.append(mat)

    def leaf(self, origin, direction, length, width, mat, roll=0):
        """Pointed, folded elliptical blade; normals vary without noisy spheres."""
        origin=Vector(origin);axis=Vector(direction).normalized()
        u=axis.cross(Vector((0,0,1)))
        if u.length < .02: u=Vector((1,0,0))
        u.normalize();n=axis.cross(u).normalized()
        lateral=u*math.cos(roll)+n*math.sin(roll)
        normal=axis.cross(lateral)
        base=len(self.verts)
        self.verts.append(tuple(origin))
        for t,w in [(.32,.82),(.65,1.0)]:
            middle=origin+axis*(length*t)+normal*(length*.07*math.sin(t*math.pi))
            self.verts.extend([tuple(middle-lateral*width*w),tuple(middle+normal*width*.15),tuple(middle+lateral*width*w)])
        self.verts.append(tuple(origin+axis*length-normal*length*.045))
        for face in [(0,1,2),(0,2,3),(1,4,5,2),(2,5,6,3),(4,7,5),(5,7,6)]:
            self.faces.append(tuple(base+i for i in face));self.mats.append(mat)

    def object(self, name, coll, materials, smooth=False, hidden=False):
        mesh=bpy.data.meshes.new(PREFIX+name+" Mesh")
        mesh.from_pydata(self.verts,[],self.faces);mesh.update()
        for mat in materials: mesh.materials.append(mat)
        for face,index in zip(mesh.polygons,self.mats):
            face.material_index=index;face.use_smooth=smooth
        obj=bpy.data.objects.new(PREFIX+name,mesh);coll.objects.link(obj)
        obj.hide_render=hidden;obj.hide_viewport=hidden
        obj["polish_owner"]="site";obj["sdb_component"]="polished_site"
        return obj


def _instance(source, name, coll, xyz, scale=(1,1,1), rotation=0):
    obj=bpy.data.objects.new(PREFIX+name,source.data);coll.objects.link(obj)
    obj.location=xyz;obj.scale=scale;obj.rotation_euler[2]=rotation
    obj["polish_owner"]="site";obj["sdb_component"]="polished_site_instance"
    return obj


def _bevel(obj, width=.03, segments=2):
    mod=obj.modifiers.new("Small manufactured edge radius","BEVEL")
    mod.width=width;mod.segments=segments
    return obj


def _ribbon(name, path, *, height, thickness, z_bottom, collection, mat, closed=False):
    """Closed walk/edging prism with actual top faces across every span.

    The legacy shaped_wall utility lacks horizontal top faces; using it for
    paving exposes underlying turf between its repeated cross section walls.
    This independent helper keeps the change local to this pass.
    """
    points=[Vector(p) for p in path]
    count=len(points);offsets=[]
    for i,point in enumerate(points):
        if not closed and i==0:
            direction=(points[1]-point).normalized();normal=Vector((-direction.y,direction.x))
        elif not closed and i==count-1:
            direction=(point-points[-2]).normalized();normal=Vector((-direction.y,direction.x))
        else:
            previous=(point-points[(i-1)%count]).normalized()
            following=(points[(i+1)%count]-point).normalized()
            n0=Vector((-previous.y,previous.x));n1=Vector((-following.y,following.x))
            normal=(n0+n1).normalized()
            normal/=max(abs(normal.dot(n1)),.5)
        offsets.append(normal*thickness*.5)
    left=[p+o for p,o in zip(points,offsets)];right=[p-o for p,o in zip(points,offsets)]
    g=Geometry()
    for z in (z_bottom,z_bottom+height):
        g.verts.extend([(p.x,p.y,z) for p in left]);g.verts.extend([(p.x,p.y,z) for p in right])
    lb,rb,lt,rt=0,count,count*2,count*3
    for i in range(count if closed else count-1):
        j=(i+1)%count
        g.faces.extend([(lt+i,rt+i,rt+j,lt+j),(lb+j,rb+j,rb+i,lb+i),
                        (lb+i,lt+i,lt+j,lb+j),(rb+j,rt+j,rt+i,rb+i)])
        g.mats.extend([0,0,0,0])
    if not closed:
        g.faces.extend([(lb,rb,rt,lt),(lb+count-1,lt+count-1,rt+count-1,rb+count-1)]);g.mats.extend([0,0])
    return g.object(name.removeprefix(PREFIX),collection,[mat])


def _make_materials():
    specifications={
        "Bark":((.115,.076,.045,1),.92,0), "Palm bark":((.23,.19,.125,1),.9,0),
        "Leaf shadow":((.028,.078,.017,1),.7,0), "Leaf olive":((.095,.19,.042,1),.63,0),
        "Leaf green":((.055,.14,.032,1),.6,0), "Leaf new growth":((.19,.285,.065,1),.57,0),
        "Palm blue green":((.07,.16,.12,1),.65,0), "Turf":((.095,.17,.042,1),.95,0),
        "Dry grass":((.255,.29,.125,1),.92,0), "Mulch":((.07,.039,.018,1),1,0),
        "Paving pale stone":((.53,.51,.44,1),.8,0), "Paving basalt":((.185,.19,.17,1),.88,0),
        "Edging stone":((.47,.45,.38,1),.8,0), "Metal graphite":((.05,.055,.048,1),.4,.72),
        "Bench teak":((.26,.115,.047,1),.54,0), "Water":((.028,.085,.055,1),.045,0),
        "Basin interior":((.058,.07,.062,1),.55,0), "Tyre":((.009,.011,.012,1),.76,0),
        "Alloy":((.37,.4,.41,1),.23,.8), "Vehicle glass":((.018,.027,.031,1),.085,.38),
        "Vehicle silver":((.34,.37,.38,1),.24,.62), "Vehicle charcoal":((.055,.064,.068,1),.21,.5),
        "Vehicle pearl":((.71,.7,.65,1),.27,.3), "Vehicle burgundy":((.21,.036,.02,1),.22,.4),
        "Headlight":((.72,.78,.72,1),.18,.22), "Tail light":((.28,.007,.006,1),.2,.2),
        "Skin":((.28,.16,.095,1),.66,0), "Hair":((.012,.01,.009,1),.75,0),
        "Shirt cream":((.56,.53,.42,1),.8,0), "Shirt grey":((.16,.19,.19,1),.8,0),
        "Trousers":((.032,.035,.042,1),.87,0), "Shoe":((.015,.012,.01,1),.5,0),
        "Flower":((.54,.12,.08,1),.75,0), "Marker white":((.68,.68,.56,1),.83,0),
    }
    mats={key:material(PREFIX+key,base_color=color,roughness=rough,metallic=metal)
          for key,(color,rough,metal) in specifications.items()}
    for key in ["Leaf shadow","Leaf olive","Leaf green","Leaf new growth","Palm blue green"]:
        bsdf=mats[key].node_tree.nodes.get("Principled BSDF")
        if "Subsurface Weight" in bsdf.inputs:bsdf.inputs["Subsurface Weight"].default_value=.055
        if "Coat Weight" in bsdf.inputs:bsdf.inputs["Coat Weight"].default_value=.08
    bsdf=mats["Water"].node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["IOR"].default_value=1.333
    if "Transmission Weight" in bsdf.inputs:bsdf.inputs["Transmission Weight"].default_value=.72
    for key,scale,strength,distance in [("Bark",14,.3,.035),("Palm bark",18,.22,.025),
                                         ("Mulch",28,.45,.025),("Turf",32,.25,.025),("Bench teak",5,.18,.004)]:
        nt=mats[key].node_tree;n=nt.nodes;link=nt.links.new
        noise=n.get("Organic surface") or n.new("ShaderNodeTexNoise");noise.name="Organic surface"
        noise.inputs["Scale"].default_value=scale;noise.inputs["Detail"].default_value=2
        bump=n.get("Micro surface") or n.new("ShaderNodeBump");bump.name="Micro surface"
        bump.inputs["Strength"].default_value=strength;bump.inputs["Distance"].default_value=distance
        link(noise.outputs["Fac"],bump.inputs["Height"]);link(bump.outputs["Normal"],n.get("Principled BSDF").inputs["Normal"])
    for key in ["Paving pale stone","Paving basalt"]:_paving_shader(mats[key],key=="Paving basalt")
    # Surface displacement is deliberately only a millimetric normal effect.
    nt=mats["Water"].node_tree;n=nt.nodes;link=nt.links.new
    noise=n.get("Fine water ripples") or n.new("ShaderNodeTexNoise");noise.name="Fine water ripples"
    noise.inputs["Scale"].default_value=23;noise.inputs["Detail"].default_value=2
    bump=n.get("Water micro normal") or n.new("ShaderNodeBump");bump.name="Water micro normal"
    bump.inputs["Strength"].default_value=.16;bump.inputs["Distance"].default_value=.006
    link(noise.outputs["Fac"],bump.inputs["Height"]);link(bump.outputs["Normal"],n.get("Principled BSDF").inputs["Normal"])
    return mats


def _paving_shader(mat,small=False):
    """Real-scale flush 6 mm paving joints, no raised strips across walks."""
    nt=mat.node_tree;n=nt.nodes;link=nt.links.new
    old=n.get("Paving coordinates")
    if old:return
    geo=n.new("ShaderNodeNewGeometry");geo.name="Paving coordinates"
    sep=n.new("ShaderNodeSeparateXYZ");link(geo.outputs["Position"],sep.inputs[0])
    def op(operation,a,b=None):
        m=n.new("ShaderNodeMath");m.operation=operation
        for i,item in enumerate([a] if b is None else [a,b]):
            if isinstance(item,(int,float)):m.inputs[i].default_value=item
            else:link(item,m.inputs[i])
        return m.outputs[0]
    width,height=(.35,.35) if small else (1.2,.6)
    row=op("FLOOR",op("DIVIDE",sep.outputs["Y"],height))
    stagger=op("MULTIPLY",op("MODULO",row,2),width*.5)
    u=op("FRACT",op("DIVIDE",op("ADD",sep.outputs["X"],stagger),width))
    v=op("FRACT",op("DIVIDE",sep.outputs["Y"],height))
    seams=op("MAXIMUM",op("LESS_THAN",u,.006/width),op("LESS_THAN",v,.006/height))
    mix=n.new("ShaderNodeMixRGB");base=tuple(mat.diffuse_color)
    mix.inputs[1].default_value=base;mix.inputs[2].default_value=tuple(c*.66 for c in base[:3])+(1,)
    link(seams,mix.inputs[0]);link(mix.outputs[0],n.get("Principled BSDF").inputs["Base Color"])
    bump=n.new("ShaderNodeBump");bump.inputs["Strength"].default_value=.2;bump.inputs["Distance"].default_value=.003
    link(seams,bump.inputs["Height"]);link(bump.outputs["Normal"],n.get("Principled BSDF").inputs["Normal"])


def _broadleaf_source(coll,mats,variant):
    """Three crown habits; foliage belongs to crooked secondary twig clusters."""
    rng=random.Random(1970+variant*293);g=Geometry()
    size=[(5.8,2.9),(6.9,3.4),(4.8,2.2)][variant];height,radius=size
    trunk=[(0,0,0),(.05,-.03,height*.24),(-.12,.11,height*.47),(.08,.06,height*.72)]
    for i in range(3):g.tube(trunk[i],trunk[i+1],.22-i*.05,.17-i*.045,0,10)
    for root in range(5):
        a=root*2*math.pi/5
        g.tube((.42*math.cos(a),.42*math.sin(a),.015),(0,0,.38),.065,.14,0,8)
    for limb in range(18):
        angle=limb*2.3999+rng.uniform(-.35,.35)
        z=height*(.42+.30*(limb%5)/4);reach=radius*rng.uniform(.62,1)
        start=Vector((0,0,z));middle=Vector((reach*.48*math.cos(angle),reach*.48*math.sin(angle),z+.44))
        endpoint=Vector((reach*math.cos(angle),reach*math.sin(angle),z+rng.uniform(.6,1.05)))
        g.tube(start,middle,.075,.038,0,7);g.tube(middle,endpoint,.038,.019,0,6)
        for twig in range(8):
            theta=angle+rng.uniform(-.9,.9);origin=middle.lerp(endpoint,.18+.78*twig/7)
            tip=origin+Vector((math.cos(theta)*.58,math.sin(theta)*.58,rng.uniform(.3,.8)))
            g.tube(origin,tip,.016,.006,0,5)
            # Uneven dense patches with air between them, not a leaf sphere skin.
            for leaf in range(90 if variant!=2 else 72):
                a=rng.random()*2*math.pi;u=rng.uniform(-1,1);r=math.sqrt(max(0,1-u*u))
                cluster=tip+Vector((math.cos(a)*r*rng.uniform(.05,.7),math.sin(a)*r*rng.uniform(.05,.7),u*.48))
                direction=(math.cos(a),math.sin(a),rng.uniform(-.65,.5))
                length=rng.uniform(.085,.17) if variant==0 else rng.uniform(.10,.21)
                width=length*(.19 if variant==0 else .3)
                tone=1+rng.choices([0,1,2,3],[18,32,42,8])[0]
                g.leaf(cluster,direction,length,width,tone,rng.uniform(-1.2,1.2))
                if variant==2 and rng.random()<.018:
                    g.ellipsoid(cluster,(.033,.033,.024),5,6,3)
    return g.object(["Neem habit tree source","Ficus habit tree source","Small flowering tree source"][variant],coll,
                    [mats["Bark"],mats["Leaf shadow"],mats["Leaf olive"],mats["Leaf green"],mats["Leaf new growth"],mats["Flower"]],hidden=True)


def _palm_source(coll,mats,fan=False):
    rng=random.Random(432 if fan else 823);g=Geometry();height=5.7 if fan else 7.5
    for j in range(22):
        a=(.16*math.sin(j*.065),.08*math.sin(j*.17),height*j/22)
        b=(.16*math.sin((j+1)*.065),.08*math.sin((j+1)*.17),height*(j+1)/22)
        radius=.22-.045*j/22
        g.tube(a,b,radius,radius*.96,0,10)
        # Visible old leaf scars are shallow rings, not a stacked cylinder tree.
        g.tube((a[0],a[1],a[2]+.012),(a[0],a[1],a[2]+.035),radius+.007,radius+.007,0,10)
    tip=Vector((.16*math.sin(22*.065),.08*math.sin(22*.17),height))
    for frond in range(24 if fan else 23):
        angle=frond*2.39996;reach=(1.9 if fan else 3.5)*rng.uniform(.82,1.1)
        prev=tip
        if fan:
            end=tip+Vector((math.cos(angle)*reach,math.sin(angle)*reach,rng.uniform(-.6,.8)))
            g.tube(tip,end,.032,.009,1,6)
            for leaflet in range(25):
                theta=angle+(leaflet-12)*.065
                g.leaf(end*.68+tip*.32,(math.cos(theta),math.sin(theta),-.12),rng.uniform(.95,1.35),.055,1+(leaflet+frond)%4,.1)
        else:
            for j in range(1,37):
                t=j/36;point=tip+Vector((math.cos(angle)*reach*t,math.sin(angle)*reach*t,.8*math.sin(math.pi*t)-1.6*t*t))
                g.tube(prev,point,.034*(1-.8*t),.031*(1-.8*t),1,5)
                for sign in (-1,1):
                    theta=angle+sign*(1.14-.3*t)
                    g.leaf(point,(math.cos(theta),math.sin(theta),-.3-.3*t),rng.uniform(.90,1.1)*(1-.58*t),.028,1+(frond+j)%4,rng.uniform(-.15,.15))
                prev=point
    return g.object("Fan palm source" if fan else "Feather palm source",coll,
                    [mats["Palm bark"],mats["Leaf shadow"],mats["Palm blue green"],mats["Leaf olive"],mats["Leaf green"]],hidden=True)


def _small_plant_sources(coll,mats):
    out={};rng=random.Random(862)
    for variant in range(3):
        g=Geometry()
        for stem in range(12):
            theta=stem*2.399;reach=rng.uniform(.15,.45);z=rng.uniform(.4,.8)
            end=(reach*math.cos(theta),reach*math.sin(theta),z)
            g.tube((0,0,0),end,.013,.006,0,5)
            for leaf in range(17):
                t=rng.uniform(.3,1);a=theta+rng.uniform(-1.9,1.9)
                pos=(end[0]*t+rng.uniform(-.13,.13),end[1]*t+rng.uniform(-.13,.13),end[2]*t)
                g.leaf(pos,(math.cos(a),math.sin(a),rng.uniform(-.4,.7)),rng.uniform(.1,.22),.028 if variant==0 else .052,1+rng.randrange(4),rng.uniform(-1,1))
        out["shrub"+str(variant)]=g.object("Shrub spray source "+str(variant+1),coll,
             [mats["Bark"],mats["Leaf shadow"],mats["Leaf olive"],mats["Leaf green"],mats["Leaf new growth"]],hidden=True)
    g=Geometry()
    for blade in range(26):
        angle=rng.uniform(0,math.pi*2);height=rng.uniform(.14,.44);offset=rng.uniform(.015,.09)
        origin=(math.cos(angle)*offset,math.sin(angle)*offset,0)
        g.leaf(origin,(math.cos(angle)*rng.uniform(.1,.8),math.sin(angle)*.4,1),height,rng.uniform(.008,.016),blade%3,rng.random())
    out["grass"]=g.object("Grass tuft source",coll,[mats["Turf"],mats["Leaf olive"],mats["Dry grass"]],hidden=True)
    return out


def _curve_points(x,y,half_y):
    """Continuous sinuous shaded garden path; stays inside the real wing void."""
    points=[]
    for j in range(61):
        t=j/60
        points.append((x+3.2+3.6*math.sin(t*math.pi*2+.32),y+half_y*(1-2*t)))
    return points


def _bed_outline(x,y,rx,ry,phase=0):
    return [(x+rx*math.cos(a)*(1+.09*math.sin(3*a+phase)),y+ry*math.sin(a)*(1+.05*math.cos(4*a+phase)))
            for a in [i*math.pi*2/40 for i in range(40)]]


def _garden(coll,mats,sources,index,court):
    x,y,rx,ry=court;rng=random.Random(235+index)
    outline=_bed_outline(x,y,rx,ry,index*.3)
    turf=polygon_prism(PREFIX+"Court %02d turf plane"%(index+1),outline,.075,.135,coll,mats["Turf"])
    turf["polish_owner"]="site"
    path=_curve_points(x,y,ry+1)
    _ribbon(PREFIX+"Court %02d flowing stone walk"%(index+1),path,height=.04,thickness=2.5,z_bottom=.14,collection=coll,mat=mats["Paving pale stone"])
    # Contrasting narrow flush band follows the edge of the path, not obstacles.
    for sign in (-1,1):
        edge=[]
        for j,p in enumerate(path):
            a=Vector(path[max(0,j-1)]);b=Vector(path[min(len(path)-1,j+1)]);d=(b-a).normalized()
            normal=Vector((-d.y,d.x));q=Vector(p)+normal*sign*1.38;edge.append(tuple(q))
        _ribbon(PREFIX+"Court %02d basalt path band"%(index+1),edge,height=.039,thickness=.21,z_bottom=.14,collection=coll,mat=mats["Paving basalt"])
    # Two long irregular planted ribbons and a small near-spine pocket.
    beds=[(x-7.0,y+12,3.3,13.5),(x+7.5,y-16,2.7,10.5),(x-5.5,y-25,3.5,4.8)]
    for bed_index,(bx,by,brx,bry) in enumerate(beds):
        points=_bed_outline(bx,by,brx,bry,bed_index+index)
        soil=polygon_prism(PREFIX+"Court %02d mulch bed %d"%(index+1,bed_index+1),points,.135,.15,coll,mats["Mulch"])
        soil["polish_owner"]="site"
        edge=_ribbon(PREFIX+"Court %02d bed edging %d"%(index+1,bed_index+1),points,height=.065,thickness=.115,z_bottom=.115,closed=True,collection=coll,mat=mats["Edging stone"])
        _bevel(edge,.012,2)
        for plant in range(30 if index==0 else 18):
            angle=rng.random()*math.pi*2;r=math.sqrt(rng.random())*.85
            px=bx+math.cos(angle)*brx*r;py=by+math.sin(angle)*bry*r
            scale=rng.uniform(.5,.92)
            _instance(sources["shrub"+str(plant%3)],"Court %02d shrub"%(index+1),coll,(px,py,.155),(scale,scale,scale*rng.uniform(.75,1.15)),rng.random()*6.28)
        # Grass is concentrated in small groups; every clump is linked-data.
        for tuft in range(65 if index==0 else 32):
            angle=rng.random()*math.pi*2;r=math.sqrt(rng.random())*.97
            px=bx+math.cos(angle)*brx*r;py=by+math.sin(angle)*bry*r
            scale=rng.uniform(.55,1.35)
            _instance(sources["grass"],"Court %02d grasses"%(index+1),coll,(px,py,.155),(scale,scale,scale),rng.random()*6.28)
    # Court trees are planted in beds; small and asymmetrically placed.
    for k,(tx,ty,variant,size) in enumerate([(x-7,y+16,index%3,.78),(x+7.6,y-21,(index+1)%3,.7),(x-6,y-25,2,.62)]):
        _instance(sources["tree"+str(variant)],"Court %02d shade tree %d"%(index+1,k+1),coll,(tx,ty,.14),(size,size,size),rng.random()*6.28)
    _fountain(coll,mats,(x-2.5,y-1.5),index)
    # Slatted bench and bins sit in little flush stone pockets beside the walk.
    for b,(bx,by,rotation) in enumerate([(x-3.8,y+8,.04),(x+4.0,y-10,math.pi)]):
        platform=polygon_prism(PREFIX+"Court bench pocket",_bed_outline(bx,by,2.0,1.05),.135,.18,coll,mats["Paving pale stone"])
        platform["polish_owner"]="site"
        for part in sources["bench"]:_instance(part,"Court %02d bench %d"%(index+1,b+1),coll,(bx,by,.18),rotation=rotation)
    # Linear slot drainage beside the spineward edge, below the walking plane.
    grate=Geometry()
    for k in range(36):grate.box((x-2.5+k*.14,y-ry+1.0,.18),(x-2.5+k*.14+.025,y-ry+1.18,.183))
    grate.object("Court %02d drainage grate"%(index+1),coll,[mats["Metal graphite"]])


def _ring(name,coll,mat,x,y,r_outer,r_inner,z0,z1,segments=64):
    g=Geometry()
    for j in range(segments):
        a=j*2*math.pi/segments;b=(j+1)*2*math.pi/segments
        def p(r,t,z):return (x+r*math.cos(t),y+r*math.sin(t),z)
        g.face([p(r_outer,a,z0),p(r_outer,b,z0),p(r_outer,b,z1),p(r_outer,a,z1)])
        g.face([p(r_inner,b,z0),p(r_inner,a,z0),p(r_inner,a,z1),p(r_inner,b,z1)])
        g.face([p(r_outer,a,z1),p(r_outer,b,z1),p(r_inner,b,z1),p(r_inner,a,z1)])
    return g.object(name,coll,[mat])


def _fountain(coll,mats,center,index):
    x,y=center
    polygon_prism(PREFIX+"Court %02d fountain paved apron"%(index+1),_bed_outline(x,y,2.6,2.6),.135,.18,coll,mats["Paving basalt"])
    rim=_ring("Court %02d real fountain basin lip"%(index+1),coll,mats["Edging stone"],x,y,1.8,1.55,.18,.45)
    _bevel(rim,.025,3)
    polygon_prism(PREFIX+"Court %02d basin bed"%(index+1),_bed_outline(x,y,1.55,1.55,0),.19,.22,coll,mats["Basin interior"])
    polygon_prism(PREFIX+"Court %02d recessed water surface"%(index+1),[(x+1.55*math.cos(j*math.pi*2/64),y+1.55*math.sin(j*math.pi*2/64)) for j in range(64)],.275,.28,coll,mats["Water"])
    # Low daytime bubblers; no opaque pointed cones masquerading as water.
    g=Geometry()
    for j in range(7):
        a=j*math.pi*2/7;px=x+.72*math.cos(a);py=y+.72*math.sin(a)
        g.tube((px,py,.21),(px,py,.27),.035,.035,0,10)
    g.object("Court %02d fountain nozzle fittings"%(index+1),coll,[mats["Metal graphite"]])
    if index==0:
        for j in range(4):_ring("Fine fountain ripple",coll,mats["Water"],x,y,.3+j*.29,.294+j*.29,.28,.284,64)


def _bench_sources(coll,mats):
    timber=Geometry();frame=Geometry()
    for j in range(5):timber.box((-1.15,-.26+j*.103,.43),(1.15,-.26+j*.103+.077,.49))
    for j in range(4):timber.box((-1.15,.23,.64+j*.098),(1.15,.292,.71+j*.098))
    for x in (-.87,.87):
        frame.box((x-.035,-.21,.015),(x+.035,-.13,.445))
        frame.box((x-.035,.18,.015),(x+.035,.25,.99))
        frame.box((x-.035,-.22,.38),(x+.035,.24,.435))
        frame.box((x-.05,-.27,.64),(x+.05,.28,.685))
        frame.box((x-.10,-.25,0),(x+.10,.27,.02))
    sources=[timber.object("Teak bench slats source",coll,[mats["Bench teak"]],hidden=True),
             frame.object("Bench powder-coated steel source",coll,[mats["Metal graphite"]],hidden=True)]
    # Modifiers are recreated on the actual instances separately if needed;
    # source data geometry already has small enough timber sections at distance.
    return sources


def _context_planting(coll,mats,sources):
    rng=random.Random(5683)
    # Reference plan has slim planted strips beside perimeter aprons. Leave
    # the south-west ramp approach reserved for the parking pass.
    strips=[(-202,-152,115,122),(-148,-104,115,122),(-94,-42,115,122),(-30,22,115,122),(38,86,115,122),
            (-158,-108,-123,-115),(-96,-40,-123,-115),(-28,28,-123,-115),(40,90,-123,-115),(102,184,-123,-115)]
    for i,(x0,x1,y0,y1) in enumerate(strips):
        polygon_prism(PREFIX+"Peripheral planted ribbon %02d"%i,[(x0,y0),(x1,y0),(x1,y1),(x0,y1)],.12,.135,coll,mats["Turf"])
        for j in range(int((x1-x0)/9)):
            x=x0+4.5+j*9;y=(y0+y1)/2
            variant=(i+j)%3;scale=rng.uniform(.58,.83)
            _instance(sources["tree"+str(variant)],"Peripheral avenue tree",coll,(x,y,.135),(scale,scale,scale),rng.random()*6.28)
        # One narrow lower layer creates a credible maintained planted edge.
        for j in range(int((x1-x0)/1.75)):
            x=x0+.8+j*1.75;y=y0+.85
            _instance(sources["shrub"+str(j%3)],"Peripheral groundcover",coll,(x,y,.14),(.7,.7,.62),rng.random()*6.28)
    # West-side court edge lies beyond the tower footprint, east club palms
    # follow the observed frontage. No trees in the entry aprons.
    for j,y in enumerate(range(-42,91,17)):
        _instance(sources["tree"+str(j%3)],"West internal shade avenue",coll,(-181,y,.13),(.84,.84,.84),rng.random()*6.28)
    for j,(x,y) in enumerate([(119,81),(127,93),(169,93),(179,73),(174,34),(132,25)]):
        _instance(sources["fan" if j%3==0 else "palm"],"Club frontage palm",coll,(x,y,.13),(.88,.88,.88),rng.random()*6.28)


def _car_source(coll,mats,color,variant=0):
    """Shaped hatch/sedan with metal roof, separate windows, tyres and lamps."""
    g=Geometry();bodymat=0;glassmat=1;rubbermat=2;alloymat=3;headmat=4;tailmat=5
    # Elliptically chamfered cross sections define bonnet, cabin and tail.
    stations=[(-2.12,.70,.53,.83),(-1.72,.84,.48,1.02),(-1.02,.88,.46,1.06),
              (.8,.87,.46,1.08),(1.68,.81,.48,.98),(2.08,.70,.52,.82)]
    rings=[]
    for x,w,z0,z1 in stations:
        base=len(g.verts)
        g.verts.extend([(x,-w*.86,z0),(x,-w,z0+.14),(x,-w,z1-.10),(x,-w*.82,z1),
                        (x,w*.82,z1),(x,w,z1-.1),(x,w,z0+.14),(x,w*.86,z0)])
        rings.append(base)
    for a,b in zip(rings,rings[1:]):
        for j in range(8):g.faces.append((a+j,a+(j+1)%8,b+(j+1)%8,b+j));g.mats.append(bodymat)
    g.faces.extend([tuple(rings[0]+i for i in reversed(range(8))),tuple(rings[-1]+i for i in range(8))]);g.mats.extend([0,0])
    front=(-.95,.75,1.0);roof_front=(-.43,.66,1.52+variant*.07);roof_rear=(.79,.66,1.51+variant*.07);rear=(1.4,.74,1.03)
    # Cabin has actual sloping front/rear glass and roof strips/body pillars.
    g.face([(front[0],-front[1],front[2]),(front[0],front[1],front[2]),(roof_front[0],roof_front[1],roof_front[2]),(roof_front[0],-roof_front[1],roof_front[2])],glassmat)
    g.face([(rear[0],rear[1],rear[2]),(rear[0],-rear[1],rear[2]),(roof_rear[0],-roof_rear[1],roof_rear[2]),(roof_rear[0],roof_rear[1],roof_rear[2])],glassmat)
    g.face([(roof_front[0],-roof_front[1],roof_front[2]),(roof_rear[0],-roof_rear[1],roof_rear[2]),(roof_rear[0],roof_rear[1],roof_rear[2]),(roof_front[0],roof_front[1],roof_front[2])],bodymat)
    for sign in (-1,1):
        g.face([(front[0],sign*front[1],1.04),(roof_front[0],sign*roof_front[1],roof_front[2]),(.18,sign*.66,roof_front[2]),(.18,sign*.765,1.06)],glassmat)
        g.face([(.26,sign*.765,1.06),(.26,sign*.66,roof_rear[2]),(roof_rear[0],sign*roof_rear[1],roof_rear[2]),(rear[0],sign*rear[1],1.06)],glassmat)
        for aa,bb in [((front[0],sign*front[1],1.03),(roof_front[0],sign*roof_front[1],roof_front[2])),
                       ((rear[0],sign*rear[1],1.03),(roof_rear[0],sign*roof_rear[1],roof_rear[2])),
                       ((.22,sign*.765,1.03),(.22,sign*.66,roof_rear[2]))]:g.tube(aa,bb,.034,.034,bodymat,6)
        for x in (-1.34,1.32):
            g.tube((x,sign*.77,.335),(x,sign*.95,.335),.335,.335,rubbermat,24)
            g.tube((x,sign*.952,.335),(x,sign*.959,.335),.23,.23,alloymat,20)
            for spoke in range(5):
                a=spoke*2*math.pi/5
                g.tube((x,sign*.963,.335),(x+.21*math.cos(a),sign*.963,.335+.21*math.sin(a)),.025,.018,alloymat,5)
            g.tube((x,sign*.965,.335),(x,sign*.97,.335),.065,.065,rubbermat,12)
        g.box((-1.02,sign*.82-.07,1.09),(-.82,sign*.82+.07,1.19),bodymat)
        for x in (-.38,.98):g.box((x,sign*.855-.014,.96),(x+.14,sign*.855+.014,.988),alloymat)
        # Lamps are solid real lens-sized pieces, not emission cubes.
        g.box((-2.13,sign*.44-.13,.72),(-2.105,sign*.44+.13,.84),headmat)
        g.box((2.065,sign*.46-.14,.71),(2.10,sign*.46+.14,.82),tailmat)
    g.box((-2.14,-.24,.57),(-2.116,.24,.64),rubbermat)
    g.box((2.086,-.22,.57),(2.112,.22,.65),rubbermat)
    return g.object("Shaped vehicle "+color+" source",coll,[mats[color],mats["Vehicle glass"],mats["Tyre"],mats["Alloy"],mats["Headlight"],mats["Tail light"]],hidden=True)


def _people_sources(coll,mats):
    """Small clothed anatomical silhouettes, intended for medium/distant views."""
    out=[]
    for pose in range(3):
        g=Geometry();skin,shirt,trousers,hair,shoe=0,1,2,3,4
        # Shoulder-to-waist tapered textile surface; no spherical snowman torso.
        base=len(g.verts)
        g.verts.extend([(-.145,-.07,.86),(.145,-.07,.86),(.145,.07,.86),(-.145,.07,.86),
                        (-.215,-.095,1.40),(.215,-.095,1.40),(.215,.095,1.40),(-.215,.095,1.40)])
        for ids in [(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7),(4,5,6,7),(0,3,2,1)]:g.faces.append(tuple(base+i for i in ids));g.mats.append(shirt)
        stride=.11 if pose else 0
        for sign in (-1,1):
            hip=(sign*.095,0,.92);knee=(sign*.095,sign*stride,.48);ankle=(sign*.105,-sign*stride,.1)
            g.tube(hip,knee,.087,.062,trousers,10);g.tube(knee,ankle,.062,.043,trousers,10)
            g.ellipsoid((sign*.105,-sign*stride-.055,.055),(.057,.13,.055),shoe,12,5)
            shoulder=(sign*.198,0,1.35);elbow=(sign*.25,.06+sign*stride,.99);hand=(sign*.24,.10-sign*stride,.79)
            if pose==2 and sign==1:elbow=(.33,-.05,1.13);hand=(.2,-.19,1.2)
            g.tube(shoulder,elbow,.064,.045,shirt,9);g.tube(elbow,hand,.042,.027,skin,9)
            g.ellipsoid(hand,(.037,.026,.063),skin,10,6)
        g.tube((0,0,1.35),(0,0,1.52),.063,.058,skin,10)
        g.ellipsoid((0,-.01,1.60),(.096,.085,.126),skin,16,10)
        # Neutral small nose/ears; no prominent cartoon facial drawing.
        g.ellipsoid((0,-.09,1.585),(.022,.028,.035),skin,8,5)
        g.ellipsoid((0,.006,1.658),(.101,.089,.082),hair,14,7)
        out.append(g.object("Distant clothed person source %d"%pose,coll,[mats["Skin"],mats["Shirt cream" if pose==0 else "Shirt grey"],mats["Trousers"],mats["Hair"],mats["Shoe"]],smooth=True,hidden=True))
    return out


def _street_details(coll,mats,sources):
    # All new ground details remain inside the plot; original roads are outside.
    paving=Geometry();dark=Geometry();mark=Geometry()
    for x0,x1 in [(-203,-152),(-148,-102),(-95,-42),(-34,25),(36,90),(99,183)]:
        paving.box((x0,108,.12),(x1,111.5,.165))
        paving.box((x0,-111.5,.12),(x1,-108,.165))
        dark.box((x0,107.7,.12),(x1,108,.17))
        dark.box((x0,-108,.12),(x1,-107.7,.17))
        # Control joints at 6m intervals and intermittent drainage inlet grilles.
        for x in range(math.ceil(x0),math.floor(x1),6):dark.box((x,108,.166),(x+.007,111.5,.168))
    paving.object("Apron pedestrian paving ribbons",coll,[mats["Paving pale stone"]])
    dark.object("Apron flush basalt trim and expansion joints",coll,[mats["Paving basalt"]])
    # Plausible curbside parking lines fit the existing north strip and leave
    # the central arrival / entrance canopies open. Their civil layout is inferred.
    for x in [-193,-186,-179,-150,-143,-136,-101,-94,-87,-41,-34,-27,21,28,35,100,107,114,180,187]:
        mark.box((x,123.0,.17),(x+.1,126.1,.174))
    mark.object("North apron thin parking bay paint",coll,[mats["Marker white"]])
    for j,(x,y,angle) in enumerate([(-189.5,124.5,0),(-146.5,124.5,0),(-97.5,124.5,0),(-37.5,124.5,0),(24.5,124.5,0),(103.5,124.5,0),(183.5,124.5,0),
                                    (-147,-119,math.pi),(-86,-119,math.pi),(61,-119,math.pi)]):
        _instance(sources["car"+str(j%4)],"Arrival vehicle %02d"%j,coll,(x,y,.12),rotation=angle)
    # Functional metal grilles inside the existing gate apertures, open leaves
    # fold along jambs; the arrival route itself stays unobstructed.
    grille=Geometry()
    for gate_x in (-8.2,8.2):
        for rail_z in (.4,1.8,3.1):grille.box((gate_x-.055,-125,rail_z-.035),(gate_x+.055,-118,rail_z+.035))
        for j in range(29):
            yy=-125+j*.245;grille.box((gate_x-.032,yy,.4),(gate_x+.032,yy+.032,3.15))
    for gate_y in (80.0,94.0):
        for rail_z in (.45,1.8,3.1):grille.box((209,gate_y-.055,rail_z-.035),(220,gate_y+.055,rail_z+.035))
        for j in range(43):
            xx=209+j*.25;grille.box((xx,gate_y-.032,.45),(xx+.035,gate_y+.032,3.15))
    _bevel(grille.object("Entry gates open metal grille leaves",coll,[mats["Metal graphite"]]),.008,1)
    # Drainage slots and small manholes on the large arrival aprons.
    grate=Geometry()
    for x in [-190,-146,-91,-31,32,104,178]:
        for y in [-107,107]:
            for j in range(13):grate.box((x+j*.085,y-.15,.16),(x+j*.085+.028,y+.15,.163))
    grate.object("Apron inlet grates",coll,[mats["Metal graphite"]])
    # Keep humans >20m from original courtyard viewpoint, avoiding portrait
    # presentation of modeled entourage. These are explicitly not scans.
    placements=[(-82,45,0),(-83,43,.2),(-91,42,2.2),(-22,71,.5),(-31,41,2.8),(40,74,1.4),
                (-107,-71,2.2),(-50,-39,1.8),(12,-75,2.9),(78,-35,.5),(127,93,.8),(133,92,2.2),(-5,-120,0),(8,-119,.4)]
    for j,(x,y,angle) in enumerate(placements):_instance(sources["person"][j%3],"Distant visitor %02d"%j,coll,(x,y,.18),rotation=angle)


def _hide_legacy():
    """Reversible and tightly scoped: retain architecture and road geometry."""
    exact={"Courtyard lawns","Low courtyard hedge grids","Courtyard benches","Courtyard bench dark frames","Perimeter parked cars"}
    prefixes=("Broadleaf tree ","Landscape palm","Court ","Low flowering shrub","Shrub linked source", "Person legs","Person torso","Person head","Person arm",
              "Parked car body","Car glazing","Car wheel")
    count=0
    for obj in bpy.data.objects:
        if obj.name.startswith(PREFIX):continue
        owned_legacy=any(c.name in {"SDB Site Vegetation","Garden detail and human scale","SDB Site Geometry","SDB Site Furniture"} for c in obj.users_collection)
        if not owned_legacy:continue
        hide=obj.name in exact or obj.name.startswith(prefixes)
        if obj.name.startswith("Courtyard ") and any(word in obj.name for word in ["curving path","circular plaza","water bowl"]):hide=True
        if hide:
            obj.hide_render=True;obj.hide_viewport=True;obj["replaced_by_site_polish"]=True;count+=1
    return count


def _clear_own(scene):
    coll=bpy.data.collections.get(COLLECTION)
    if coll is None:coll=bpy.data.collections.new(COLLECTION)
    if scene.collection.children.get(coll.name) is None:scene.collection.children.link(coll)
    for obj in list(coll.all_objects):
        data=obj.data;bpy.data.objects.remove(obj,do_unlink=True)
        if data and data.users==0:
            if isinstance(data,bpy.types.Mesh):bpy.data.meshes.remove(data)
            elif isinstance(data,bpy.types.Camera):bpy.data.cameras.remove(data)
            elif isinstance(data,bpy.types.Curve):bpy.data.curves.remove(data)
    return coll


def apply(scene=None):
    scene=scene or bpy.context.scene
    coll=_clear_own(scene);mats=_make_materials();sources={}
    hidden=_hide_legacy()
    for variant in range(3):sources["tree"+str(variant)]=_broadleaf_source(coll,mats,variant)
    sources["palm"]=_palm_source(coll,mats);sources["fan"]=_palm_source(coll,mats,True)
    sources.update(_small_plant_sources(coll,mats));sources["bench"]=_bench_sources(coll,mats)
    for variant,color in enumerate(["Vehicle silver","Vehicle charcoal","Vehicle pearl","Vehicle burgundy"]):
        sources["car"+str(variant)]=_car_source(coll,mats,color,variant%2)
    sources["person"]=_people_sources(coll,mats)
    for index,court in enumerate(COURTS):_garden(coll,mats,sources,index,court)
    _context_planting(coll,mats,sources);_street_details(coll,mats,sources)
    # Optional detail view; no mutation of the existing production cameras.
    data=bpy.data.cameras.new(PREFIX+"Courtyard detail Camera");data.lens=32;data.clip_end=2000
    camera=bpy.data.objects.new("CAM Courtyard detail",data);coll.objects.link(camera)
    camera.location=(-82,99,1.85);point_at(camera,(-88,60,2.7));camera["polish_owner"]="site"
    objects=list(coll.objects);unique={o.data.as_pointer():o.data for o in objects if o.type=="MESH"}
    stats={"collection":COLLECTION,"objects":len(objects),"mesh_objects":sum(o.type=="MESH" for o in objects),
           "unique_meshes":len(unique),"unique_vertices":sum(len(m.vertices) for m in unique.values()),
           "unique_polygons":sum(len(m.polygons) for m in unique.values()),"legacy_objects_hidden":hidden,
           "courtyards":len(COURTS),"tree_variants":5,"parking_exclusion":PARKING_EXCLUSION,
           "reference_scope":"Photographic landscape character; inferred exact planting species, civil details, furniture and site dimensions"}
    scene["SDB Site Polish metadata"]=json.dumps(stats)
    return stats
