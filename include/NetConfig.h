#pragma once
#include <stdint.h>
#include <string.h>
#include <stdio.h>
struct NetConfig {uint32_t magic=0x414e5731;char ssid[33]={},password[65]={},host[16]={},token[17]={};};
inline bool validNet(const NetConfig& c){
 if(c.magic!=0x414e5731||!memchr(c.ssid,0,33)||!memchr(c.password,0,65)||!memchr(c.host,0,16)||!memchr(c.token,0,17))return false;
 if(!c.ssid[0])return true;
 unsigned a,b,d,e;char tail;if(sscanf(c.host,"%u.%u.%u.%u%c",&a,&b,&d,&e,&tail)!=4||a>255||b>255||d>255||e>255)return false;
 if(strlen(c.token)!=16)return false;
 for(int i=0;i<16;i++)if(!((c.token[i]>='0'&&c.token[i]<='9')||(c.token[i]>='a'&&c.token[i]<='f')))return false;
 return true;
}
