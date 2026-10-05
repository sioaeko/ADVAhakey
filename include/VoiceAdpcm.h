#pragma once
#include <stdint.h>
#include <stddef.h>
namespace aha {
// Independent 20ms IMA ADPCM block: predictor:s16le, index:u8,
// then 319 low-nibble-first codes; final high nibble is zero.
// 163 payload + 19 AVP1 bytes = 182, one notification at ATT MTU185.
static const int ImaSteps[89]={7,8,9,10,11,12,13,14,16,17,19,21,23,25,28,31,34,37,41,45,50,55,60,66,73,80,88,97,107,118,130,143,157,173,190,209,230,253,279,307,337,371,408,449,494,544,598,658,724,796,876,963,1060,1166,1282,1411,1552,1707,1878,2066,2272,2499,2749,3024,3327,3660,4026,4428,4871,5358,5894,6484,7132,7845,8630,9493,10442,11487,12635,13899,15289,16818,18500,20350,22385,24623,27086,29794,32767};
static const int ImaIndex[8]={-1,-1,-1,-1,2,4,6,8};
inline void encodeVoiceAdpcm(const int16_t* pcm,uint8_t out[163],int& index){
 int predicted=pcm[0];out[0]=predicted&255;out[1]=(uint16_t(predicted)>>8);out[2]=index;
 for(unsigned i=3;i<163;i++)out[i]=0;
 for(unsigned i=1;i<320;i++){
  int step=ImaSteps[index],delta=int(pcm[i])-predicted,code=0,difference=step>>3;
  if(delta<0){code=8;delta=-delta;}
  if(delta>=step){code|=4;delta-=step;difference+=step;}
  step>>=1;if(delta>=step){code|=2;delta-=step;difference+=step;}
  step>>=1;if(delta>=step){code|=1;difference+=step;}
  predicted+=(code&8)?-difference:difference;
  if(predicted>32767)predicted=32767;if(predicted<-32768)predicted=-32768;
  index+=ImaIndex[code&7];if(index<0)index=0;if(index>88)index=88;
  out[3+(i-1)/2]|=uint8_t(code<<(((i-1)&1)*4));
 }
}
}
