from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

OUT = Path(r"C:\Users\dell\Documents\Codex\2026-11-05\new-chat\outputs\grantbridge-feature-preview.png")
W, H = 1900, 1120
im = Image.new("RGB", (W, H), "#111a36")
d = ImageDraw.Draw(im)
for yy in range(H):
    d.line((0, yy, W, yy), fill=(15 + yy // 150, 23 + yy // 170, 48 + yy // 70))
try:
    regular = ImageFont.truetype(r"C:\Windows\Fonts\segoeui.ttf", 12)
    bold = ImageFont.truetype(r"C:\Windows\Fonts\seguisb.ttf", 12)
except OSError:
    regular = bold = ImageFont.load_default()
NAVY="#101a35"; PURPLE="#5b5dde"; INK="#18213a"; MUTED="#7d8598"; WHITE="#ffffff"; BG="#f5f6fa"; LINE="#e9ecf3"; LILAC="#ededff"; GREEN="#22845e"
def txt(x,y,s,n=11,c=INK,b=False,anchor=None):
    f=regular if n==12 else ImageFont.truetype(r"C:\Windows\Fonts\seguisb.ttf" if b else r"C:\Windows\Fonts\segoeui.ttf", n)
    d.text((x,y),s,font=f,fill=c,anchor=anchor)
def rr(box,r,fill,outline=None,w=1): d.rounded_rectangle(box,r,fill=fill,outline=outline,width=w)
def card(x,y,w,h): rr((x,y,x+w,y+h),15,WHITE,LINE)
def phone(x, title, active):
    top=192
    rr((x,top,x+370,top+800),39,"#0d1120",outline="#5c6379",w=2); rr((x+8,top+8,x+362,top+792),32,BG)
    d.rectangle((x+9,top+10,x+361,top+40),fill=WHITE); txt(x+24,top+18,"9:41",10,INK,True)
    d.rectangle((x+9,top+40,x+361,top+94),fill=WHITE); rr((x+22,top+52,x+53,top+83),9,PURPLE); txt(x+37,top+67,"G",19,WHITE,True,"mm")
    txt(x+61,top+51,"GRANTBRIDGE",12,INK,True); txt(x+61,top+69,title,10,MUTED)
    rr((x+315,top+52,x+346,top+83),10,"#f1f1fa"); d.arc((x+325,top+59,x+335,top+72),190,350,fill=PURPLE,width=2); d.line((x+325,top+66,x+325,top+73,x+335,top+73,x+335,top+66),fill=PURPLE,width=2)
    d.rectangle((x+9,top+714,x+361,top+763),fill=WHITE); d.line((x+9,top+714,x+361,top+714),fill=LINE)
    navlabels=["Home","Discover","Team","Docs","Profile"]
    for i,label in enumerate(navlabels):
        cx=x+35+i*70; col=PURPLE if label==active else "#9299aa"
        if label==active: rr((cx-15,top+718,cx+15,top+742),8,LILAC)
        if label=="Home": d.line((cx-8,top+732,cx,top+725,cx+8,top+732),fill=col,width=2); d.line((cx-6,top+731,cx-6,top+739,cx+6,top+739,cx+6,top+731),fill=col,width=2)
        elif label=="Discover": d.ellipse((cx-7,top+724,cx+3,top+734),outline=col,width=2); d.line((cx+2,top+733,cx+8,top+739),fill=col,width=2)
        elif label=="Team": d.ellipse((cx-3,top+724,cx+4,top+731),outline=col,width=2); d.arc((cx-9,top+729,cx+10,top+743),180,355,fill=col,width=2)
        elif label=="Docs": d.rounded_rectangle((cx-6,top+724,cx+6,top+740),2,outline=col,width=2); d.line((cx-3,top+729,cx+3,top+729),fill=col,width=1); d.line((cx-3,top+733,cx+3,top+733),fill=col,width=1)
        else: d.ellipse((cx-4,top+724,cx+4,top+732),outline=col,width=2); d.arc((cx-8,top+729,cx+8,top+744),185,355,fill=col,width=2)
        txt(cx,top+746,label,9,col,label==active,"mm")
    rr((x+128,top+772,x+228,top+775),3,"#222637")
    return x+9, top+94

txt(62,42,"GRANTBRIDGE",16,WHITE,True); txt(62,70,"Android app · interactive feature preview",30,WHITE,True)
txt(62,116,"Funding reports · team communication · document center",14,"#b9c3dd")
xs=[35,495,955,1415]
for x,lab in zip(xs,["HOME · RECOMMENDED FUNDING","FUNDING REPORT · GRANT SCOUT","TEAM · SHARED ROOM","DOCS · EVIDENCE LIBRARY"]): txt(x+5,164,lab,10,"#aaa8ff",True)

# Home / recommended funding
x,y=phone(xs[0],"Your funding workspace","Home")
txt(x+17,y+18,"Welcome back,",10,MUTED); txt(x+17,y+35,"Riverbend Learning Trust",16,INK,True)
rr((x+14,y+64,x+338,y+194),18,"#192549"); txt(x+28,y+80,"MOVE YOUR MISSION FORWARD",9,"#c7c4ff",True); txt(x+28,y+103,"Funding with a team",17,WHITE,True); txt(x+28,y+125,"that keeps people in the loop",12,WHITE); rr((x+28,y+151,x+186,y+178),8,"#7778f2"); txt(x+107,y+165,"Explore funding  →",9,WHITE,True,"mm")
txt(x+16,y+216,"Recommended funding",13,INK,True); txt(x+335,y+217,"See all  ›",9,PURPLE,True,"ra")
for yy,title,funder,amount in [(y+239,"Digital Learning Access Fund","Northstar Foundation","Up to $40,000"),(y+389,"Connected Communities Fund","Horizon Impact Partners","$15,000–$60,000")]:
    card(x+14,yy,324,137); rr((x+26,yy+13,x+62,yy+49),10,LILAC); d.ellipse((x+37,yy+22,x+51,yy+37),outline=PURPLE,width=2); txt(x+74,yy+13,"SAMPLE · EDUCATION",8,PURPLE,True); txt(x+74,yy+32,title,10,INK,True); txt(x+74,yy+51,funder,8,MUTED); d.line((x+26,yy+75,x+326,yy+75),fill=LINE); txt(x+26,yy+86,amount,9,INK,True); rr((x+26,yy+107,x+326,yy+129),7,PURPLE); txt(x+176,yy+118,"View report and details",8,WHITE,True,"mm")
rr((x+14,y+540,x+338,y+619),13,"#fff7e6",outline="#f0e3c7"); txt(x+27,y+555,"Before you apply",10,"#8b621d",True); txt(x+27,y+575,"Confirm the deadline and eligibility",9,"#786b52"); txt(x+27,y+590,"on the funder's official page.",9,"#786b52")

# Funding report / avatar and pathway
x,y=phone(xs[1],"Funding report","Discover")
txt(x+16,y+16,"Funding report",19,INK,True); txt(x+16,y+42,"SAMPLE OPPORTUNITY",8,PURPLE,True)
card(x+14,y+61,324,126); txt(x+27,y+75,"Digital Learning Access Fund",13,INK,True); txt(x+27,y+98,"Northstar Community Foundation",9,MUTED); txt(x+27,y+125,"Funding",8,MUTED); txt(x+27,y+141,"Up to $40,000",12,INK,True); txt(x+190,y+125,"Deadline",8,MUTED); txt(x+190,y+141,"Jul 02, 2026",10,INK,True); txt(x+27,y+168,"Education",9,PURPLE,True)
card(x+14,y+199,324,82); rr((x+26,y+213,x+77,y+264),25,"#625dd8"); d.ellipse((x+37,y+224,x+66,y+253),outline=WHITE,width=2); d.ellipse((x+43,y+230,x+49,y+236),fill=WHITE); d.ellipse((x+55,y+241,x+60,y+246),fill="#9be5d2"); txt(x+89,y+213,"Grant Scout",12,INK,True); txt(x+89,y+234,"AI opportunity analyst",9,PURPLE,True); txt(x+89,y+251,"Funder facts and requirements organized",8,MUTED)
txt(x+16,y+300,"Application pathway",12,INK,True); card(x+14,y+321,324,145)
for i,(label,sub) in enumerate([("Opportunity review","Now"),("Eligibility and evidence","After you start"),("Budget review","Team review"),("Draft and compliance","Human approval")]):
    yy=y+335+i*30; d.ellipse((x+27,yy,x+47,yy+20),fill=LILAC if i==0 else "#f0f2f6"); txt(x+37,yy+10,"✓" if i==0 else str(i+1),9,PURPLE if i==0 else MUTED,True,"mm"); txt(x+58,yy+1,label,9,INK,True); txt(x+321,yy+3,sub,7,MUTED,False,"ra")
txt(x+16,y+475,"Listed requirements",12,INK,True); card(x+14,y+496,324,60)
for i,label in enumerate(["Registered nonprofit","Education project","Registration certificate"]): txt(x+28,y+505+i*15,"•  "+label,8,INK if i==0 else MUTED)
rr((x+14,y+566,x+338,y+601),9,PURPLE); txt(x+176,y+584,"Start application with my team",9,WHITE,True,"mm")

# Team room
x,y=phone(xs[2],"People and messages","Team")
txt(x+16,y+18,"Your team",19,INK,True); txt(x+16,y+44,"People and AI specialists",9,MUTED)
card(x+14,y+65,324,145); txt(x+27,y+78,"ORGANIZATION MEMBERS · 2",9,PURPLE,True)
for i,(initial,name,role) in enumerate([("AM","Asha Mehta","Owner"),("RK","Ravi Kumar","Grant Writer")]):
    yy=y+101+i*51; rr((x+26,yy,x+60,yy+34),17,LILAC); txt(x+43,yy+17,initial,8,PURPLE,True,"mm"); txt(x+72,yy+1,name,10,INK,True); txt(x+72,yy+20,role,8,MUTED)
txt(x+16,y+229,"AI grant specialists",12,INK,True)
card(x+14,y+251,324,101)
for i,name in enumerate(["Grant Scout","Eligibility Analyst","Budget Analyst"]):
    yy=y+261+i*28; rr((x+25,yy,x+46,yy+21),11,"#625dd8" if i==0 else LILAC); txt(x+36,yy+10,"✦" if i==0 else name[:2].upper(),7,WHITE if i==0 else PURPLE,True,"mm"); txt(x+56,yy+4,name,9,INK)
txt(x+16,y+362,"Team room · shared with invited members",9,INK,True)
rr((x+14,y+373,x+308,y+439),13,WHITE,LINE); rr((x+25,y+384,x+53,y+412),14,LILAC); txt(x+39,y+398,"RK",7,PURPLE,True,"mm"); txt(x+64,y+383,"Ravi Kumar",9,INK,True); txt(x+64,y+402,"The registration file is uploaded.",8,INK); txt(x+64,y+418,"9:32 AM",7,MUTED)
rr((x+63,y+450,x+338,y+509),13,"#ededff"); txt(x+76,y+461,"You",8,PURPLE,True); txt(x+76,y+481,"Thanks, I’ll review it today.",8,INK); txt(x+318,y+496,"9:35 AM",7,MUTED,False,"ra")
rr((x+14,y+532,x+338,y+586),13,WHITE,LINE); txt(x+27,y+550,"Message the team…",9,MUTED); rr((x+296,y+542,x+326,y+572),15,PURPLE); d.line((x+305,y+557,x+317,y+557),fill=WHITE,width=2); d.line((x+312,y+552,x+317,y+557,x+312,y+562),fill=WHITE,width=2)

# Documents
x,y=phone(xs[3],"Evidence and files","Docs")
txt(x+16,y+18,"Document center",18,INK,True); txt(x+16,y+43,"Evidence and shared files",9,MUTED)
for i,(lab,val) in enumerate([("Files","08"),("Text checked","06")]):
    bx=x+14+i*165; card(bx,y+66,157,63); txt(bx+12,y+78,lab,8,MUTED); txt(bx+12,y+97,val,18,INK,True)
card(x+14,y+143,324,115); txt(x+27,y+156,"ADD A DOCUMENT",9,PURPLE,True); rr((x+26,y+178,x+326,y+206),7,"#f7f8fb",LINE); txt(x+38,y+187,"Attach to Application #12  ▾",8,INK); rr((x+26,y+215,x+326,y+246),8,PURPLE); txt(x+176,y+230,"↑  Choose a file",9,WHITE,True,"mm")
card(x+14,y+273,324,38); txt(x+27,y+286,"⌕   Search files",9,MUTED)
for i,(label,w) in enumerate([("All",45),("Registration",91),("Budget",62)]):
    bx=x+14+sum([45,91,62][:i])+i*7; rr((bx,y+324,bx+w,y+348),12,PURPLE if i==0 else WHITE,LINE); txt(bx+w/2,y+336,label,7,WHITE if i==0 else MUTED,True,"mm")
txt(x+16,y+361,"FILES · 8",9,INK,True)
for i,(name,cat,state) in enumerate([("registration_certificate.pdf","Registration","Text checked"),("2026_project_budget.xlsx","Budget","Stored for review"),("learner_outcomes.pdf","Impact evidence","Text checked")]):
    yy=y+382+i*73; card(x+14,yy,324,63); rr((x+25,yy+14,x+54,yy+46),8,LILAC); txt(x+39,yy+30,"▤",11,PURPLE,True,"mm"); txt(x+65,yy+10,name,8,INK,True); txt(x+65,yy+28,cat,8,MUTED); txt(x+65,yy+44,state,7,GREEN if "checked" in state else "#aa6a24")
txt(x+16,y+615,"Evidence checklist · confirm funder requirements",8,MUTED)

txt(W//2,H-18,"Android UI concept · diagrams and sample content · not an emulator capture",11,"#a6b2ce",False,"mm")
OUT.parent.mkdir(parents=True,exist_ok=True); im.save(OUT); print(OUT)
