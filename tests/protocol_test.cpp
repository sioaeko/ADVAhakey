#include "StickyFn.h"
#include "Protocol.h"
#include "Gate.h"
#include "InputRouter.h"
#include "OriginalDefaults.h"
#include "NetConfig.h"
#include <cassert>
#include <cstdio>
#include <random>
int main(){
 using namespace aha;
 {
 StickyFn f;auto one=keyBit(1,0);
 assert(f.update(Fn,0)==Fn);assert(f.update(0,10)==0&&f.pending());
 assert(f.update(one,20)==(Fn|one));assert(!f.pending());
 assert(f.update(one,30)==(Fn|one));assert(f.update(0,40)==0);
 assert(f.update(one,50)==one);f.update(0,60);
 f.update(Fn,70);f.update(0,80);assert(f.update(0,90,true)&Fn);
 assert(!f.pending());assert(f.update(0,100)==0);
 f.update(Fn,110);f.update(one|Fn,120);f.update(0,130);assert(!f.pending());
 f.update(Fn,140);f.update(0,150);f.update(Fn,160);f.update(0,170);assert(!f.pending());
 f.update(Fn,180);f.update(0,190);assert(f.update(one,5190)==one);
 f.update(Fn,5200);f.reset(Fn);f.update(0,5210);assert(!f.pending());
 }
 Gate gate;assert(gate.value()==1);gate.press(100);gate.tick(1599,true);assert(gate.value()==1);gate.tick(1600,true);assert(gate.value()==0);
 gate.release();gate.tick(1700,true);assert(gate.value()==0);gate.tick(1800,false);assert(gate.value()==1);
 gate.press(0);gate.release();gate.tick(2000,true);assert(gate.value()==1);
 gate.press(0xfffffff0);gate.tick(0x5cc,true);assert(gate.value()==0);gate.reset();assert(gate.value()==1);
 NetConfig net;assert(validNet(net));strcpy(net.ssid,"home");assert(!validNet(net));
 strcpy(net.host,"192.168.1.10");strcpy(net.token,"0123456789abcdef");assert(validNet(net));
 strcpy(net.host,"192.168.1.256");assert(!validNet(net));strcpy(net.host,"192.168.1.1x");assert(!validNet(net));
 strcpy(net.host,"192.168.1.10");net.token[0]='z';assert(!validNet(net));
 InputRouter router;
 auto digit=keyBit(1,0);assert(router.update(digit).keys==digit);
 auto routed=router.update(Fn|digit);assert(routed.shortcut==0&&!(routed.keys&digit));
 routed=router.update(digit);assert(routed.shortcut==-1&&!(routed.keys&digit));
 router.update(0);assert(router.update(digit).keys==digit);
 assert(router.update(Fn|Space).voice);assert(!router.update(Space).voice);assert(!(router.update(Space).keys&Space));
 router.update(0);assert(router.update(Space).keys==Space);
 assert(router.update(Fn|Tab).nextMode);assert(!router.update(Fn|Tab).nextMode);
 router.update(0);assert(router.update(Tab).keys==Tab);
 assert(fnUsage(0,0)==0x29&&fnUsage(5,0)==0x3e&&fnUsage(11,2)==0x52);
 const uint8_t crcText[]="123456789";assert(crc32(crcText,9)==0xcbf43926);
 uint8_t query[]={0xaa,0xbb,0,0xcc,0xdd};assert(frame(query,5));
 for(int n=0;n<5;n++)assert(!frame(query,n));
 uint8_t shortcut[]={0x73,3,3,0xe0,6};assert(valid(0x73,shortcut,5));shortcut[1]=4;assert(!valid(0x73,shortcut,5));
 uint8_t macro[]={0x74,0,0,1,4,3,255,2,4,4,0};assert(valid(0x73,macro,11));assert(!valid(0x73,macro,10));macro[3]=5;assert(!valid(0x73,macro,11));
 uint8_t pic[]={0,10,0,70,0,100,0};assert(valid(0x82,pic,7));pic[3]=71;assert(!valid(0x82,pic,7));pic[3]=70;pic[5]=0;assert(!valid(0x82,pic,7));
 uint8_t prepare[]={0,0,16,0,0,0,0};assert(valid(0x80,prepare,7));prepare[3]=1;assert(!valid(0x80,prepare,7));prepare[3]=0;prepare[2]=17;assert(!valid(0x80,prepare,7));
 Config original;originalDefaults(original);assert(validConfig(original));
 assert(original.keys[0][0].data[0]==0x6d&&original.keys[0][1].data[0]==0x28);
 assert(original.keys[0][2].type==0x74&&original.keys[0][2].length==12);
 assert(original.keys[1][2].data[0]==0x2a&&original.keys[2][2].data[0]==0x29);
 auto customized=original;strcpy(customized.keys[0][0].label,"Custom");customized.keys[0][0].data[0]=4;
 migratePrototypeDefaults(customized);assert(customized.keys[0][0].data[0]==4&&!strcmp(customized.keys[0][0].label,"Custom"));
 auto untouched=original;strcpy(untouched.keys[0][0].label,"Approve Enter");untouched.keys[0][0].data[0]=0x28;
 migratePrototypeDefaults(untouched);assert(untouched.keys[0][0].data[0]==0x6d);
 for(int fx=0;fx<=16;fx++){bool lit=false;for(int tick=0;tick<512;tick++){
  LightRGB out[8];originalLightFrame(fx,35,out);for(auto c:out){lit|=c.r||c.g||c.b;if(fx==0)assert(!(c.r||c.g||c.b));}
 }if(fx)assert(lit);}
 Config cfg;assert(validConfig(cfg));cfg.mode=4;assert(!validConfig(cfg));cfg.mode=0;cfg.keys[0][0].length=99;assert(!validConfig(cfg));
 std::mt19937 random(7364);uint8_t buffer[512];
 for(int i=0;i<100000;i++){for(auto& b:buffer)b=random();size_t n=random()%512;frame(buffer,n);valid(uint8_t(random()),buffer,n);}
 puts("Protocol boundaries and 100000 malformed input probes passed");
}
