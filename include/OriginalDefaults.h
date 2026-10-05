// Modified from AhakeyAI/desktop APP/sub_main/main.c defaults.
// Ported to this project's configuration types; see NOTICE (Apache-2.0).
#pragma once
#include "Protocol.h"
#include "OriginalLights.h"
namespace aha {
inline void originalKeys(Config& c) {
 const char* names[4][4]={{"Record","Yes","No","Backspace"},{"Record","Accept","Reject","Backspace"},{"Record","Accept","Reject","Backspace"},{"N/A","N/A","N/A","N/A"}};
 for(int m=0;m<4;m++)for(int k=0;k<4;k++) {
  Key& key=c.keys[m][k];key=Key{};memset(key.data,0,sizeof(key.data));strcpy(key.label,names[m][k]);
  key.length=m==3?0:1;
  key.data[0]=k==0?0x6d:k==1?0x28:0x2a;
  if(m==2&&k==2)key.data[0]=0x29;
  if(m==0&&k==2){const uint8_t macro[]={1,0x51,2,0x51,1,0x51,2,0x51,1,0x28,2,0x28};key.type=0x74;key.length=sizeof(macro);memcpy(key.data,macro,sizeof(macro));}
 }
}
inline void originalDefaults(Config& c) {
 originalKeys(c);c.brightness=35;
 for(auto& effects:c.effects)memcpy(effects,OriginalEffects,9);
}
// Migrate only exact untouched prototype bindings; never replace customized keys.
inline void migratePrototypeDefaults(Config& c) {
 Config original;originalDefaults(original);
 const char* labels[]={"Approve Enter","Reject Esc","Copy","Paste"};
 const uint8_t data[4][2]={{0x28,0},{0x29,0},{0xe0,0x06},{0xe0,0x19}};
 for(int m=0;m<4;m++)for(int k=0;k<4;k++) {
  auto& key=c.keys[m][k];unsigned n=k<2?1:2;
  if(key.type==0x73&&key.length==n&&!strcmp(key.label,labels[k])&&!memcmp(key.data,data[k],n))key=original.keys[m][k];
 }
 const uint8_t effects[]={11,16,12,13,6,0,12,7,0};
 for(auto& row:c.effects)if(!memcmp(row,effects,9))memcpy(row,OriginalEffects,9);
}
}
