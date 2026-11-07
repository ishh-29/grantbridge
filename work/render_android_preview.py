from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

OUT = Path(r"C:\Users\dell\Documents\Codex\2026-11-05\new-chat\outputs\grantbridge-android-preview.png")
W, H = 1500, 1050
im = Image.new("RGB", (W, H), "#111a36")
d = ImageDraw.Draw(im)
for y in range(H):
    col = (15 + y//130, 23 + y//150, 50 + y//60)
    d.line((0,y,W,y), fill=col)
try:
    regular=ImageFont.truetype(r"C:\Windows\Fonts\segoeui.ttf", 12)
    medium=ImageFont.truetype(r"C:\Windows\Fonts\seguisb.ttf", 12)
except OSError:
    regular=ImageFont.load_default(); medium=regular
def text(x,y,s,size=12,color="#17213a",bold=False,anchor=None):
    f=medium if bold else regular
    if size!=12:
        try: f=ImageFont.truetype(r"C:\Windows\Fonts\seguisb.ttf" if bold else r"C:\Windows\Fonts\segoeui.ttf", size)
        except OSError: pass
    d.text((x,y),s,font=f,fill=color,anchor=anchor)
def rr(box,r,fill,outline=None,width=1): d.rounded_rectangle(box,r,fill=fill,outline=outline,width=width)
NAVY="#101a35"; PURPLE="#5a5cdd"; INK="#18213a"; MUTED="#7c8498"; WHITE="#fff"; BG="#f5f6fa"; LINE="#e9ecf3"; GREEN="#20845e"; LILAC="#ededff"
def phone(x,y,title):
    rr((x,y,x+370,y+780),42,"#0d1120",outline="#626982",width=2)
    rr((x+8,y+8,x+362,y+772),35,BG)
    d.rectangle((x+9,y+10,x+361,y+40),fill=WHITE)
    text(x+26,y+19,"9:41",11,INK,True)
    d.arc((x+305,y+18,x+313,y+26),200,340,fill=INK,width=1); d.line((x+309,y+18,x+309,y+26),fill=INK,width=1)
    d.rectangle((x+319,y+20,x+325,y+25),outline=INK,width=1); d.rectangle((x+329,y+18,x+338,y+25),outline=INK,width=1); d.rectangle((x+330,y+19,x+336,y+24),fill=INK)
    d.rectangle((x+9,y+40,x+361,y+94),fill=WHITE)
    rr((x+22,y+52,x+53,y+83),9,PURPLE); text(x+37,y+67,"G",19,WHITE,True,"mm")
    text(x+61,y+51,"GRANTBRIDGE",12,INK,True); text(x+61,y+69,title,10,MUTED)
    rr((x+315,y+52,x+346,y+83),10,"#f1f1fa")
    d.arc((x+325,y+59,x+335,y+72),190,350,fill=PURPLE,width=2); d.line((x+325,y+66,x+325,y+73,x+335,y+73,x+335,y+66),fill=PURPLE,width=2); d.ellipse((x+329,y+74,x+331,y+76),fill=PURPLE)
    return x+9,y+94
def card(x,y,w,h,fill=WHITE):
    rr((x,y,x+w,y+h),15,fill,LINE,1)
def nav(x,y,active):
    d.rectangle((x,y+620,x+352,y+668),fill=WHITE); d.line((x,y+620,x+352,y+620),fill=LINE)
    names=["Home","Discover","Team","Docs","Profile"]
    for i,n in enumerate(names):
        cx=x+35+i*70; c=PURPLE if n==active else "#9299aa"
        if n==active: rr((cx-15,y+625,cx+15,y+649),8,LILAC)
        if n=="Home":
            d.line((cx-8,y+638,cx,y+631,cx+8,y+638),fill=c,width=2,joint="curve"); d.line((cx-6,y+637,cx-6,y+645,cx+6,y+645,cx+6,y+637),fill=c,width=2)
        elif n=="Discover":
            d.ellipse((cx-7,y+630,cx+3,y+640),outline=c,width=2); d.line((cx+2,y+639,cx+8,y+645),fill=c,width=2)
        elif n=="Team":
            d.ellipse((cx-3,y+630,cx+4,y+637),outline=c,width=2); d.arc((cx-9,y+635,cx+10,y+649),180,355,fill=c,width=2); d.ellipse((cx-10,y+632,cx-5,y+637),outline=c,width=1)
        elif n=="Docs":
            d.rounded_rectangle((cx-6,y+630,cx+6,y+646),2,outline=c,width=2); d.line((cx-3,y+635,cx+3,y+635),fill=c,width=1); d.line((cx-3,y+639,cx+3,y+639),fill=c,width=1)
        else:
            d.ellipse((cx-4,y+630,cx+4,y+638),outline=c,width=2); d.arc((cx-8,y+635,cx+8,y+650),185,355,fill=c,width=2)
        text(cx,y+655,n,9,c,n==active,"mm")
    rr((x+126,y+672,x+226,y+675),3,"#222637")

# Title and screen labels
text(72,40,"GRANTBRIDGE",16,WHITE,True)
text(72,67,"Android application preview",30,WHITE,True)
text(72,112,"Jetpack Compose · Human-led grant preparation · Sample data",14,"#b9c3dd")
xs=[65,565,1065]
for x,label in zip(xs,["HOME · OVERVIEW","DISCOVER · GRANTS","PROFILE · ACCOUNT"]): text(x+5,154,label,11,"#aaa8ff",True)

# Home screen
x,y=phone(xs[0],180,"Your funding workspace")
text(x+18,y+17,"Welcome back,",11,MUTED); text(x+18,y+35,"Riverbend Learning Trust",18,INK,True)
rr((x+14,y+64,x+338,y+214),19,"#192549")
text(x+29,y+81,"FUND THE NEXT CHAPTER",9,"#c7c4ff",True)
text(x+29,y+103,"Move your mission",17,WHITE,True); text(x+29,y+124,"forward with a thoughtful team",13,WHITE,True)
text(x+29,y+151,"Evidence, people, and funding in one workspace.",9,"#d4d8eb")
rr((x+29,y+174,x+195,y+202),9,"#7778f2"); text(x+112,y+188,"Start an application  →",10,WHITE,True,"mm")
text(x+16,y+232,"Your workspace",13,INK,True)
for i,(lab,val,small) in enumerate([("Applications","02","1 needs review"),("Profile","82%","Almost complete")]):
    bx=x+14+i*165; card(bx,y+254,157,82); text(bx+11,y+266,lab,10,MUTED); text(bx+11,y+282,val,23,INK,True); text(bx+11,y+315,small,9,GREEN)
text(x+16,y+352,"Upcoming deadline",13,INK,True)
card(x+14,y+374,324,62); rr((x+25,y+384,x+63,y+426),8,LILAC); text(x+44,y+392,"JUN",8,PURPLE,True,"mm"); text(x+44,y+412,"18",14,INK,True,"mm")
text(x+74,y+385,"Bright Futures Fund",11,INK,True); text(x+74,y+406,"Education · 12 days left",9,MUTED)
text(x+16,y+453,"Recommended funding",13,INK,True)
card(x+14,y+476,324,82); rr((x+25,y+489,x+60,y+524),10,LILAC); d.line((x+42,y+495,x+42,y+518),fill=PURPLE,width=2); d.line((x+31,y+506,x+53,y+506),fill=PURPLE,width=2); d.line((x+35,y+499,x+49,y+513),fill=PURPLE,width=1); d.line((x+49,y+499,x+35,y+513),fill=PURPLE,width=1)
text(x+70,y+486,"SAMPLE · EDUCATION",8,PURPLE,True); text(x+70,y+503,"Digital Learning Access Fund",11,INK,True); text(x+70,y+523,"Northstar Community Foundation",9,MUTED); text(x+70,y+541,"Up to $40,000",9,INK,True)
text(x+16,y+548,"Recent team activity",13,INK,True)
card(x+14,y+570,324,58); rr((x+24,y+583,x+54,y+613),15,LILAC); text(x+39,y+598,"EA",9,PURPLE,True,"mm"); text(x+63,y+581,"Eligibility Analyst",10,INK,True); text(x+63,y+600,"Registration evidence added",9,MUTED); text(x+63,y+616,"9 minutes ago",8,MUTED)
nav(x,y,"Home")

# Discover screen
x,y=phone(xs[1],180,"Find your next opportunity")
text(x+16,y+20,"Discover grants",20,INK,True); text(x+16,y+48,"Funding opportunities matched to your mission.",10,MUTED)
card(x+14,y+72,324,41); d.ellipse((x+27,y+83,x+37,y+93),outline="#969daf",width=1); d.line((x+36,y+92,x+41,y+97),fill="#969daf",width=1); text(x+47,y+86,"Search grants or funders",10,"#969daf")
rr((x+14,y+124,x+94,y+149),13,LILAC); text(x+54,y+137,"Education",9,PURPLE,True,"mm")
rr((x+101,y+124,x+152,y+149),13,WHITE,LINE); text(x+126,y+137,"India",9,MUTED,False,"mm")
text(x+16,y+162,"3 opportunities · best match first",9,MUTED)
def grant(y0,tag,title,funder,amount,date):
    card(x+14,y0,324,150); text(x+27,y0+13,tag,8,PURPLE,True); text(x+27,y0+34,title,12,INK,True); text(x+27,y0+54,funder,9,MUTED)
    d.line((x+27,y0+79,x+325,y0+79),fill=LINE)
    text(x+27,y0+90,amount,10,INK,True); text(x+325,y0+91,date,9,MUTED,False,"ra")
    rr((x+27,y0+113,x+325,y0+140),8,"#5b5dde"); text(x+176,y0+126,"View details · Start application",9,WHITE,True,"mm")
grant(y+188,"SAMPLE · EDUCATION","Digital Learning Access Fund","Northstar Community Foundation","$10k–$40k","Jul 02, 2026")
grant(y+353,"SAMPLE · COMMUNITY","Connected Communities Initiative","Horizon Impact Partners","$15k–$60k","Aug 14, 2026")
card(x+14,y+520,324,65,"#fff7e6"); text(x+28,y+535,"Check the official source",10,"#8b621d",True); text(x+28,y+554,"Dates and eligibility can change. Imported grants",8,"#786b52"); text(x+28,y+568,"are labeled unverified until checked by a person.",8,"#786b52")
nav(x,y,"Find")

# Profile screen with nested sections and a visible team card
x,y=phone(xs[2],180,"Your account and organization")
text(x+16,y+16,"Your profile",19,INK,True); text(x+16,y+42,"Manage your details and grant workspace.",9,MUTED)
card(x+14,y+62,324,91)
rr((x+26,y+78,x+72,y+124),23,LILAC); text(x+49,y+100,"AM",15,PURPLE,True,"mm")
text(x+84,y+79,"Asha Mehta",13,INK,True); text(x+84,y+99,"asha@riverbend.org",9,MUTED); text(x+84,y+119,"OWNER · RIVERBEND TRUST",8,PURPLE,True)
rr((x+14,y+166,x+338,y+199),12,"#f0efff")
for i,(label,w) in enumerate([("Profile",62),("Personal",67),("Organization",92),("Team",48)]):
    bx=x+18+sum([62,67,92,48][:i])+i*5
    rr((bx,y+171,bx+w,y+194),8,PURPLE if label=="Profile" else WHITE)
    text(bx+w/2,y+182,label,7,WHITE if label=="Profile" else MUTED,label=="Profile","mm")
text(x+16,y+215,"YOUR ORGANIZATION",8,PURPLE,True)
card(x+14,y+233,324,108)
text(x+27,y+246,"Riverbend Learning Trust",12,INK,True); text(x+27,y+266,"Nonprofit · India · Registered",9,MUTED)
text(x+27,y+287,"Education access for rural learners",9,INK)
rr((x+27,y+309,x+317,y+320),5,"#eceef5"); rr((x+27,y+309,x+250,y+320),5,PURPLE)
text(x+27,y+326,"Organization profile 78% complete",8,MUTED)
text(x+16,y+359,"TEAM ACCESS",8,PURPLE,True)
card(x+14,y+377,324,58)
rr((x+26,y+389,x+56,y+419),15,LILAC); text(x+41,y+404,"RK",8,PURPLE,True,"mm")
text(x+66,y+389,"Ravi Kumar",10,INK,True); text(x+66,y+408,"Grant Writer · Member",8,MUTED); text(x+319,y+404,"›",16,MUTED,False,"mm")
card(x+14,y+446,324,58)
rr((x+26,y+458,x+56,y+488),15,"#e8f6ef"); text(x+41,y+473,"PN",8,GREEN,True,"mm")
text(x+66,y+458,"Priya Nair",10,INK,True); text(x+66,y+477,"Program Lead · Admin",8,MUTED); text(x+319,y+473,"›",16,MUTED,False,"mm")
rr((x+14,y+516,x+338,y+553),10,"#5b5dde"); d.line((x+140,y+534,x+152,y+534),fill=WHITE,width=2); d.line((x+146,y+528,x+146,y+540),fill=WHITE,width=2); text(x+226,y+534,"Invite a teammate",10,WHITE,True,"mm")
card(x+14,y+565,324,47)
text(x+27,y+579,"Personal details",9,INK,True); text(x+317,y+589,"Edit  ›",8,PURPLE,True,"ra")
nav(x,y,"Profile")

text(W//2,H-20,"Android screen preview · nested navigation · bundled SVG bottom icons · illustrative data · not an emulator screenshot",11,"#a6b2ce",False,"mm")
OUT.parent.mkdir(parents=True,exist_ok=True)
im.save(OUT)
print(OUT)
