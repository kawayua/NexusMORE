import fs from 'node:fs/promises';
import path from 'node:path';
import {FileBlob,SpreadsheetFile} from '@oai/artifact-tool';
const folder=path.resolve(process.argv[2]);
const data=JSON.parse(await fs.readFile(path.join(folder,'workbook-input.json'),'utf8'));
const workbook=await SpreadsheetFile.importXlsx(await FileBlob.load(data.template));
const sheet=workbook.worksheets.getItem('Sheet1');
if(process.argv[3]==='preview'){
 const image=await workbook.render({sheetName:'Sheet1',range:'A1:D14',scale:1.5,format:'png'});
 await fs.writeFile(path.join(folder,'template-preview.png'),new Uint8Array(await image.arrayBuffer()));
 console.log('original template preview rendered without edits');process.exit(0);
}
const before=sheet.getRange('A1:D225').values;
if(before.length!==225)throw new Error('template row count differs');
const beforeLabels=before.map(row=>row[0]);
sheet.getRange('B2:D225').values=data.values;
sheet.getRange('B2:D225').format.numberFormat='0.000000';
await workbook.recalculate();
const after=sheet.getRange('A1:A225').values.map(row=>row[0]);
if(JSON.stringify(beforeLabels)!==JSON.stringify(after))throw new Error('row labels changed');
const blob=await SpreadsheetFile.exportXlsx(workbook);await blob.save(path.join(folder,'results/result2.xlsx'));
const preview=await workbook.render({sheetName:'Sheet1',range:'A1:D14',scale:1.5,format:'png'});
await fs.writeFile(path.join(folder,'results/result2-preview.png'),new Uint8Array(await preview.arrayBuffer()));
await fs.writeFile(path.join(folder,'workbook-export.json'),JSON.stringify({authoring:'@oai/artifact-tool',template_imported:true,range:'Sheet1!B2:D225',rows:224,numeric_columns:3,number_format:'0.000000',row_labels_preserved:true,preview:'results/result2-preview.png'},null,2));
console.log('result2 actual template patched with artifact-tool; labels preserved');
