-- Typed views over ppp.raw_* (loaded by load.sh). Views show the latest round of each page; older rows stay in raw_rows.
create or replace function ppp.num(t text) returns numeric language sql immutable as $$
  select case when replace(t, ',', '') ~ '^\s*-?\d+(\.\d+)?\s*$' then replace(t, ',', '')::numeric end $$;

create or replace function ppp.dt(t text) returns date language plpgsql immutable as $$
declare m text;
begin
  m := substring(t from '\d{1,2}[.\-/]\d{1,2}[.\-/]\d{4}');
  if m is not null then return to_date(regexp_replace(m, '[.\-/]', '.', 'g'), 'DD.MM.YYYY'); end if;
  m := substring(t from '\d{1,2}[ \-,]+[A-Za-z]{3,9}[ \-,]+\d{4}');
  if m is not null then return to_date(regexp_replace(left(regexp_replace(m, '([A-Za-z]{3})[A-Za-z]*', '\1'), 20), '[ \-,]+', ' ', 'g'), 'DD Mon YYYY'); end if;
  return null;
exception when others then return null;
end $$;

create or replace view ppp.cur as
select r.record_id, r.data->>'page' as page, r.data->'fields' as f, r.data->'docs' as docs, r.data->>'url' as url,
       (r.data->>'pipeline_id')::int as pipeline_id, r.data->>'round' as round
from ppp.raw_rows r
join (select data->>'page' as page, max(data->>'round') as round from ppp.raw_rows group by 1) l
  on l.page = r.data->>'page' and l.round = r.data->>'round';

create or replace view ppp.pppac as
select record_id, f->>'Project Name' as project, f->>'Sponsoring Authority' as authority, f->>'Location' as location,
       f->>'Sector' as sector, f->>'Sub Sector' as sub_sector, ppp.num(f->>'Total Project Cost (In Rs. Crore)') as tpc_cr,
       ppp.dt(f->>'PPPAC Meeting Date') as meeting_date, substring(f->>'Meeting Number' from '\d+')::int as meeting_no,
       f->>'Recommended For' as recommended_for, docs
from ppp.cur where page = 'pppac-projects-list';

create or replace view ppp.consolidated as
select record_id, f->>'Project Name' as project, f->>'Location' as location, f->>'Sector' as sector,
       ppp.num(f->>'Total Project Cost(in Rs. Crore)') as tpc_cr, ppp.dt(f->>'Approval') as approval_date,
       substring(f->>'Approval' from '(\d+)\s*(?:st|nd|rd|th)\s')::int as meeting_no,
       substring(f->>'Approval' from '(PPPAC|EC|EI|SFC|IIPDF)') as body, f->>'Implementing Authority' as authority, docs
from ppp.cur where page = 'consolidated';

create or replace view ppp.vgf_inprinciple as
select record_id, f->>'Project Name' as project, f->>'Location' as location, f->>'Sector' as sector,
       ppp.num(f->>'Total Project Cost (In Rs. Crore)') as tpc_cr, ppp.num(f->>'VGF Approved (In Rs. Crore)') as vgf_cr,
       ppp.dt(f->>'In Principle Meeting Date') as meeting_date, substring(f->>'In Principle Meeting Number' from '\d+')::int as ec_no,
       f->>'Implementing Authority' as authority, docs
from ppp.cur where page = 'vgf-inprinciple-project-list';

create or replace view ppp.vgf_final as
select record_id, f->>'Project Name' as project, f->>'Location' as location, f->>'Sector' as sector,
       ppp.num(f->>'Total Project Cost (In Rs. Crore)') as tpc_cr, ppp.num(f->>'Total VGF Approved (In Rs. Crore)') as vgf_total_cr,
       ppp.num(f->>'VGF Approved by DEA CAPEX (In Rs. Crore)') as dea_capex_cr, ppp.num(f->>'VGF Approved by DEA OPEX (In Rs. Crore)') as dea_opex_cr,
       ppp.num(f->>'VGF Released till date by DEA for CAPEX (In Rs. Crore)') as dea_released_cr,
       ppp.num(f->>'VGF Approved by State CAPEX (In Rs. Crore)') as state_capex_cr, ppp.num(f->>'VGF Approved by State OPEX (In Rs. Crore)') as state_opex_cr,
       ppp.dt(right(f->>'In Principle Meeting Date', 10)) as ip_date, substring(f->>'In Principle Meeting Number' from '\d+')::int as ip_ec_no,
       ppp.dt(f->>'Final Approval Meeting Date') as final_date, substring(f->>'Final Approval Meeting Number' from '\d+')::int as final_ec_no,
       f->>'Implementing Authority' as authority, f->>'Latest Status' as status, docs
from ppp.cur where page = 'vgf-final-project-list';

create or replace view ppp.signed_ca as
select record_id, f->>'Project Name' as project, f->>'Project Authority' as authority, f->>'Concessionaire' as concessionaire,
       f->>'Location' as location, f->>'Sector' as sector, ppp.dt(f->>'Date of Signing of Concession Agreement') as signed_on,
       f->>'Date of Signing of Concession Agreement' as signed_raw, docs
from ppp.cur where page = 'signed-concession-agreements';

create or replace view ppp.pipeline as
select record_id, pipeline_id, page, f->>'Name of Project' as project, f->>'Project Sponsoring Authority' as authority,
       f->>'Department' as department, f->>'Sector/Sub Sector (as per HML)' as sector, f->>'PPP Model' as model,
       ppp.num(f->>'Total Project Cost (in Rs Cr)') as tpc_cr, f->>'Location' as location, f->>'Project Stage' as stage,
       f->>'Likely Bid Date' as likely_bid, f
from ppp.cur where page like 'ppp-projects-pipeline-department-%' or page like 'ppp-projects-pipeline-states-yearwise-%';

create or replace view ppp.infra as
select record_id, f->>'Project Name' as project, ppp.num(f->>'Total Project Cost (In Rs.Crore)') as tpc_cr, f->>'Sector' as sector,
       f->>'Sub-Sector' as sub_sector, f->>'Project Authority' as authority, ppp.dt(f->>'Date Of Award') as awarded_on,
       f->>'Location' as location, f->>'Status' as status
from ppp.cur where page = 'all-infrastructure-projects';

create or replace view ppp.docs as
select record_id, data->>'kind' as kind, data->>'url' as url, data->>'page' as page, data->>'file' as file,
       (data->>'bytes')::bigint as bytes, (data->>'pages')::int as pdf_pages, (data->>'has_text')::boolean as has_text,
       (data->>'ocr_needed')::boolean as ocr_needed, data->>'last_modified' as last_modified, (data->>'status')::int as http_status,
       data->>'sha256' as sha256, data->>'bucket_path' as bucket_path, data->>'text_path' as text_path, data->'rows' as row_ids
from ppp.raw_docs where data->>'kind' in ('doc', 'missing');

create or replace view ppp.old as
select (data->>'old_id')::int as old_id, data->>'mode' as mode, data->>'captured' as captured, data->>'wayback_url' as wayback_url,
       data->'fields'->>'Project Name' as project, data->'fields'->>'Name Of Authority' as authority,
       coalesce(data->'fields'->>'Name Of Concessionaire', data->'fields'->>'Name Of Contractor') as partner,
       data->'fields'->>'Type of PPP' as ppp_type, data->'fields'->>'Location' as location, data->'fields'->>'Sector' as sector,
       data->'fields'->>'Project Status' as status,
       ppp.num(coalesce(data->'fields'->>'Project Cost (as per Concession Agreement) in Rs Crore', data->'fields'->>'Project Cost (as per Contract) in Rs Crore')) as cost_contract_cr,
       ppp.num(data->'fields'->>'Project Cost (Revised) in Rs Crore') as cost_revised_cr,
       ppp.num(coalesce(data->'fields'->>'Project Cost (Actual) in Rs Crore', data->'fields'->>'Project Cost(Actual) in Rs Crore')) as cost_actual_cr,
       ppp.dt(coalesce(data->'fields'->>'Concession Agreement Signing Date', data->'fields'->>'Date Of Award Of Project')) as awarded_on,
       ppp.num(data->'fields'->>'Concession Duration (In Months)') as concession_months, data->'fields'->>'Bid Parameter' as bid_parameter,
       data->'fields'->>'Type Of Grant' as grant_type, ppp.num(data->'fields'->>'Grant Amount in Rs Crore') as grant_cr, data->'fields' as fields
from ppp.raw_old where data->>'kind' in ('old_project', 'old_project_pdf');

-- small materialized copies with trigram indexes (fuzzy name joins); load.sh rebuilds them
create extension if not exists pg_trgm;
do $$ declare v text; begin
  foreach v in array array['pppac','consolidated','vgf_inprinciple','vgf_final','signed_ca','pipeline','infra','old'] loop
    execute format('drop table if exists ppp.m_%s', v);
    execute format('create table ppp.m_%s as select * from ppp.%s', v, v);
    execute format('create index on ppp.m_%s using gin (lower(project) gin_trgm_ops)', v);
  end loop; end $$;
