// Replays explicit reviewer gestures on the real image editor, not injected masks.
export async function drawBox(page,box){
 const area=await page.getByTestId('highlight-canvas').boundingBox();
 await page.getByRole('button',{name:'Draw box',exact:true}).click();
 await page.mouse.move(area.x+box.x*area.width,area.y+box.y*area.height);
 await page.mouse.down();
 await page.mouse.move(area.x+(box.x+box.width)*area.width,area.y+(box.y+box.height)*area.height,{steps:12});
 await page.mouse.up();
}
export async function drawStroke(page,stroke){
 await page.getByRole('button',{name:stroke.kind==='include'?'Include stroke':'Exclude stroke',exact:true}).click();
 await page.getByRole('slider',{name:'Stroke width'}).fill(String(stroke.width));
 const area=await page.getByTestId('highlight-canvas').boundingBox();
 for(let n=0;n<stroke.points.length;n++){
  const p=stroke.points[n];await page.mouse.move(area.x+p.x*area.width,area.y+p.y*area.height);
  if(n===0)await page.mouse.down();
 }
 await page.mouse.up();
}
