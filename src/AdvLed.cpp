#include "AdvLed.h"
#include <driver/rmt.h>
// Arduino ESP32 2.x uses legacy RMT; M5Unified 0.2.21 only implements the IDF5 path.
static constexpr rmt_channel_t channel=RMT_CHANNEL_0;
bool beginAdvLed(){
 rmt_config_t cfg=RMT_DEFAULT_CONFIG_TX(GPIO_NUM_21,channel);
 cfg.clk_div=2; // 40 MHz, 25 ns per tick.
 if(rmt_config(&cfg)!=ESP_OK)return false;
 return rmt_driver_install(channel,0,0)==ESP_OK;
}
bool writeAdvLed(uint8_t r,uint8_t g,uint8_t b){
 const uint8_t grb[]={g,r,b};rmt_item32_t items[25]{};
 for(unsigned i=0;i<24;i++){
  bool bit=grb[i/8]&(0x80>>(i%8));
  items[i].level0=1;items[i].duration0=bit?28:14;
  items[i].level1=0;items[i].duration1=bit?24:32;
 }
 items[24].level0=0;items[24].duration0=6000;
 items[24].level1=0;items[24].duration1=6000;
 return rmt_write_items(channel,items,25,true)==ESP_OK;
}
