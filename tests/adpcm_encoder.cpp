#include "VoiceAdpcm.h"
#include <stdio.h>
int main(int argc,char** argv){
 if(argc!=3)return 2;
 FILE* in=fopen(argv[1],"rb");FILE* out=fopen(argv[2],"wb");if(!in||!out)return 3;
 int16_t pcm[320];uint8_t block[163];int index=0;size_t n;
 while((n=fread(pcm,sizeof(int16_t),320,in))==320){
  aha::encodeVoiceAdpcm(pcm,block,index);if(fwrite(block,1,sizeof(block),out)!=sizeof(block))return 4;
 }
 bool ok=n==0&&!ferror(in);fclose(in);fclose(out);return ok?0:5;
}
