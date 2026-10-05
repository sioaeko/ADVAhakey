#pragma once
#include <stdint.h>
namespace aha {
constexpr uint64_t keyBit(int x,int y){return uint64_t(1)<<(y*14+x);}
constexpr uint64_t Fn=keyBit(0,2), Space=keyBit(13,3), Tab=keyBit(0,1);
struct InputResult {uint64_t keys=0;int shortcut=-1;bool voice=false, nextMode=false;};
class InputRouter {
 uint64_t suppressed=0;bool lastTab=false;
 public:
 InputResult update(uint64_t raw){
  InputResult r; suppressed&=raw;
  if(raw&Fn){
   for(int i=0;i<4;i++)if(raw&keyBit(i+1,0)){r.shortcut=i;suppressed|=keyBit(i+1,0);break;}
   r.voice=raw&Space;if(r.voice)suppressed|=Space;
   bool tab=raw&Tab;r.nextMode=tab&&!lastTab;if(tab)suppressed|=Tab;lastTab=tab;
  }else lastTab=false;
  r.keys=raw&~suppressed;
  return r;
 }
};
inline uint8_t fnUsage(int x,int y){
 if(y==0){if(x==0)return 0x29;if(x<=12)return 0x39+x;return 0x4c;}
 if(y==2&&x==11)return 0x52;
 if(y==3&&x>=10&&x<=12){const uint8_t arrows[]={0x50,0x51,0x4f};return arrows[x-10];}
 return 0;
}
inline uint32_t crc32(const uint8_t* p,unsigned n){uint32_t c=~0u;while(n--){c^=*p++;for(int i=0;i<8;i++)c=(c>>1)^(0xedb88320u&uint32_t(-int32_t(c&1)));}return ~c;}
}
