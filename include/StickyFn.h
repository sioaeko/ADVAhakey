#pragma once
#include "InputRouter.h"
namespace aha {
class StickyFn {
 bool down_=false,used_=false,armed_=false;
 uint64_t held_=0;uint32_t armedAt_=0;
 public:
 bool pending() const{return armed_;}
 void reset(uint64_t raw){down_=raw&Fn;used_=true;armed_=false;held_=0;}
 uint64_t update(uint64_t raw,uint32_t now,bool externalPress=false){
  bool down=raw&Fn;uint64_t others=raw&~Fn;
  held_&=others;
  if(armed_&&uint32_t(now-armedAt_)>=5000)armed_=false;
  if(down&&!down_){used_=armed_;armed_=false;}
  if(down&&(others||externalPress))used_=true;
  if(!down&&down_&&!used_){armed_=true;armedAt_=now;}
  down_=down;
  bool externalFn=externalPress&&(down||armed_);
  if(armed_&&(others||externalPress)){
   armed_=false;held_=others;
  }
  return raw|((held_||externalFn)?Fn:0);
 }
};
}
