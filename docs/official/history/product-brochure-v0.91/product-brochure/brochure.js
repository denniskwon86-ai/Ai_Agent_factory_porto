(function(){
  const delay=document.querySelector('#delayRange');
  const price=document.querySelector('#priceRange');
  if(!delay||!price)return;
  const set=(id,value)=>{const el=document.querySelector(id);if(el)el.textContent=value};
  function render(){
    const d=Number(delay.value);const p=Number(price.value);
    const stock=-(d*0.23);const production=-(d*0.23+p*0.16);const sales=-(d*0.55+p*0.47);const cash=-(d*0.82+p*0.71);
    set('#delayValue',`${d}일`);set('#priceValue',`${p>=0?'+':''}${p}%`);set('#arrivalImpact',`+${d}일`);
    set('#stockImpact',`${stock.toFixed(1)}일`);set('#productionImpact',`${production.toFixed(1)}%`);
    set('#salesImpact',`${sales.toFixed(1)}억`);set('#cashImpact',`${cash.toFixed(1)}억`);
    set('#scenarioBrief',`${d}일 지연과 ${p}% 가격 변동을 함께 반영했습니다. 생산 차질과 현금 위험을 동시에 낮추는 조합입니다.`);
  }
  delay.addEventListener('input',render);price.addEventListener('input',render);render();
})();
