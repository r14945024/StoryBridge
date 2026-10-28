"""Generate an original, synthetic short-film illustration for the licensed-free demo.
8 scenes * 8 seconds = 64 seconds. No third-party footage or portrait assets.
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import subprocess
import random
import math
import shutil

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT/'media'
ASSET = ROOT/'assets'
OUT.mkdir(exist_ok=True)
ASSET.mkdir(exist_ok=True)
FONT = '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
if not Path(FONT).exists():
    FONT = '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc'
W,H=960,540
font=lambda n: ImageFont.truetype(FONT,n)


def rounded(draw, box, radius, fill, outline=None, width=1):
    draw.rounded_rectangle(box,radius=radius,fill=fill,outline=outline,width=width)

def line(draw,coords,fill,width=5):draw.line(coords,fill=fill,width=width,joint='curve')

def draw_library(im,draw):
    draw.rectangle((0,0,W,H),fill='#263444')
    # sunset glow
    for i in range(70):
        draw.ellipse((650-i*3,-150-i*3,980+i*3,280+i*3),outline=(95,72,55),width=2)
    draw.rectangle((0,354,960,540),fill='#3a3335')
    draw.polygon([(0,350),(960,350),(960,420),(0,425)],fill='#474047')
    for j in range(4):
        x=45+j*200
        rounded(draw,(x,68,x+164,336),10,'#172433','#526077',3)
        for row in range(3):
            yy=104+70*row
            line(draw,(x+7,yy+46,x+157,yy+46),'#6c5660',5)
            for k in range(9):
                xx=x+13+k*16
                c=['#aa876f','#728e91','#b19f75','#66657c','#728489'][((k*3)+row+j)%5]
                draw.rectangle((xx,yy-4,xx+11,yy+42),fill=c)
    # table
    draw.ellipse((194,362,780,451),fill='#171f2a')
    rounded(draw,(195,332,762,390),20,'#9a674b','#d79c6c',4)
    line(draw,(245,385,228,508),'#5b3d3b',15);line(draw,(716,385,730,508),'#5b3d3b',15)

def draw_hallway(im,draw):
    draw.rectangle((0,0,W,H),fill='#263a4a')
    draw.polygon([(0,0),(245,110),(245,458),(0,540)],fill='#304457')
    draw.polygon([(960,0),(755,110),(755,458),(960,540)],fill='#1d2d3e')
    draw.polygon([(245,110),(755,110),(755,458),(245,458)],fill='#344858')
    draw.polygon([(245,458),(755,458),(960,540),(0,540)],fill='#253544')
    for x in [120,840]:
        rounded(draw,(x-45,160,x+45,396),6,'#182a3a','#6a7e8d',5)
        draw.ellipse((x+21,270,x+29,278),fill='#e2af74')
    draw.ellipse((412,408,547,478),fill='#1c2d3a')
    for y in [490,511,533]:line(draw,(0,y,960,y),'#2f4152',2)
    rounded(draw,(426,45,533,85),14,'#d8b785','#8b7050')
    draw.text((481,49),'走廊',font=font(24),fill='#263440',anchor='mt')

def draw_person(draw,x,y,role='an',costume='gray',pose='normal',key=False,size=1.0):
    # Person anchor: x,y is ground foot; flat vector cartoon character
    def p(xx,yy):return (int(x+xx*size),int(y+yy*size))
    skin='#dca878' if role=='an' else '#dfac8d'
    color={'gray':'#8c96a8','blue':'#3976b1','yellow':'#edbf64'}[costume]
    # shadow
    draw.ellipse((*p(-41,0),*p(44,12)),fill='#162432')
    # trouser legs
    for ox in [-16,11]:line(draw,(*p(ox,-91),*p(ox-2,-2)),'#232c46',15)
    draw.ellipse((*p(-28,-6),*p(-5,7)),fill='#141e2a');draw.ellipse((*p(3,-6),*p(31,7)),fill='#141e2a')
    # coat / torso
    draw.polygon([p(-47,-205),p(37,-205),p(34,-90),p(-40,-90)],fill=color)
    line(draw,(*p(-2,-203),*p(-2,-93)),'#becad0' if costume=='blue' else color,3)
    # arms
    if pose=='take':
        line(draw,(*p(30,-186),*p(74,-135)),'#dca878',13);draw.ellipse((*p(67,-141),*p(82,-125)),fill=skin)
    elif pose=='point':
        line(draw,(*p(-38,-181),*p(-87,-165)),'#dca878',12);draw.ellipse((*p(-92,-169),*p(-78,-156)),fill=skin)
    elif pose=='give':
        line(draw,(*p(29,-177),*p(102,-160)),skin,12);draw.ellipse((*p(96,-166),*p(109,-154)),fill=skin)
    else:
        line(draw,(*p(-42,-189),*p(-50,-103)),skin,13);line(draw,(*p(33,-189),*p(47,-103)),skin,13)
    # neck + head
    rounded(draw,(*p(-8,-232),*p(8,-207)),5,skin)
    draw.ellipse((*p(-31,-281),*p(32,-221)),fill=skin)
    if role=='an':
        draw.pieslice((*p(-33,-292),*p(35,-227)),182,355,fill='#172331')
        draw.polygon([p(-30,-260),p(-28,-292),p(17,-297),p(37,-271),p(8,-282)],fill='#182230')
    else:
        rounded(draw,(*p(-38,-292),*p(39,-217)),20,'#201d2e')
        draw.ellipse((*p(-30,-281),*p(31,-223)),fill=skin)
        draw.pieslice((*p(-30,-290),*p(33,-238)),180,355,fill='#1e1c2e')
    draw.ellipse((*p(-15,-257),*p(-10,-252)),fill='#222e3a');draw.ellipse((*p(12,-257),*p(17,-252)),fill='#222e3a')
    line(draw,(*p(-6,-241),*p(7,-240)),'#9c6e65',2)
    # small identification pill, intentionally visible as drama labels
    name='小安' if role=='an' else '小晴'
    rounded(draw,(*p(-30,-326),*p(33,-297)),9,'#182b3d','#739db1')
    draw.text(p(0,-324),name,font=font(max(12,round(17*size))),fill='#edf2f9',anchor='mt')
    if key:draw_key(draw,*p(90,-139),scale=size)

def draw_key(draw,x,y,scale=1):
    r=round(11*scale)
    draw.ellipse((x-r,y-r,x+r,y+r),outline='#ffdf84',width=max(3,round(5*scale)))
    line(draw,(x+r-3,y+2,x+40*scale,y+20*scale),'#f5cb66',max(4,round(6*scale)))
    line(draw,(x+34*scale,y+15*scale,x+34*scale,y+32*scale),'#f5cb66',max(3,round(5*scale)))

def scene(idx):
    im=Image.new('RGB',(W,H));d=ImageDraw.Draw(im)
    scene_id=idx+1
    islib=idx in [0,1,2,7]
    (draw_library if islib else draw_hallway)(im,d)
    if idx==0:
        draw_person(d,320,407,'an','gray',size=.87);draw_person(d,660,407,'qing','yellow',size=.87)
        draw_key(d,485,341,.75)
    elif idx==1:
        draw_person(d,405,440,'an','gray','take',size=.94);draw_key(d,500,321,.73)
    elif idx==2:
        draw_person(d,600,435,'qing','yellow','normal',size=.92)
        d.ellipse((438,322,518,338),outline='#f3bd69',width=2)
    elif idx==3:
        draw_person(d,500,489,'an','blue',size=1.20)
    elif idx==4:
        draw_person(d,500,489,'an','blue',size=1.20)
        rounded(d,(534,337,554,385),6,'#1d5285','#82b3d4')
        draw_key(d,545,351,.42)
    elif idx==5:
        draw_person(d,407,490,'an','blue',size=1.12)
        draw_person(d,652,486,'qing','yellow','point',size=1.07)
    elif idx==6:
        draw_person(d,387,494,'an','blue','give',size=1.11)
        draw_person(d,660,492,'qing','yellow',size=1.09)
        draw_key(d,504,328,.78)
    else:
        draw_person(d,322,430,'an','blue',size=.92)
        draw_person(d,650,430,'qing','yellow',size=.92)
        draw_key(d,490,339,.8)
    # cinematic top / bottom gradient bars
    d.rectangle((0,0,960,31),fill='#101a25');d.rectangle((0,508,960,540),fill='#101a25')
    d.text((30,10),'STORYBRIDGE · ORIGINAL DEMO',font=font(13),fill='#9bbac8')
    d.text((925,10),f'SCENE {scene_id:02d}/08',font=font(13),fill='#a5d8dc',anchor='ra')
    subtitles=['圖書館 · 相遇','圖書館 · 鑰匙','圖書館 · 發現','走廊 · 換裝','走廊 · 口袋','走廊 · 追問','走廊 · 歸還','圖書館 · 結局']
    rounded(d,(22,455,245,496),12,'#0a152acc','#55778a')
    d.text((37,465),subtitles[idx],font=font(18),fill='#e6f6ff')
    return im


def main():
    for i in range(8):
        img=scene(i)
        img.save(ASSET/f'scene_{i+1:02}.png',optimize=True)
    scene(0).save(ASSET/'cover.png')
    concat=ASSET/'concat.txt'
    with concat.open('w',encoding='utf-8') as f:
        for i in range(8):
            f.write(f"file 'scene_{i+1:02}.png'\n")
            f.write('duration 8\n')
        f.write("file 'scene_08.png'\n")
    ffmpeg=shutil.which('ffmpeg')
    if not ffmpeg:raise RuntimeError('需要安裝 ffmpeg 才能重新產生示範影片')
    # Original ambient soundtrack, no dialogue or copyrighted music.
    cmd=[ffmpeg,'-hide_banner','-loglevel','error','-y','-safe','0','-f','concat','-i',str(concat),
         '-f','lavfi','-i','sine=frequency=196:sample_rate=44100:duration=64',
         '-filter_complex','[1:a]volume=0.012[aout]',
         '-map','0:v','-map','[aout]','-vf','fps=12,format=yuv420p',
         '-c:v','libx264','-preset','veryfast','-crf','26','-c:a','aac','-b:a','48k','-t','64','-movflags','+faststart',str(OUT/'demo_story.mp4')]
    subprocess.run(cmd,check=True)
    print('Generated:',OUT/'demo_story.mp4',(OUT/'demo_story.mp4').stat().st_size,'bytes')

if __name__=='__main__':main()
