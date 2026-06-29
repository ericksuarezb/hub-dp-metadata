-- ___________________________________________________________________________________________________________________________________
--/     #####   PROYECTO CRYSTAL DATA   #####
--| @FECHA DE CREACION:
--|     # Martes, 24 de Febrero del 2026
--| @DOMINIOS:                          
--|     # Captacion
--| @ARCHIVO:                           
--|     # 01_cd_cap_cuenta_delta.sql 
--| @AUTOR:                                     
--|     # Erick Suarez Buendia <erick.suarez@algorithia.com>
--|	# Brenda Sarahi Rosas Morán <brenda.rosasm@algorithia.com>
--| @DESCRIPCION:                        
--|     # 
--| @TIEMPOS DE EJECUCION:      
--|     # 
--| @MODIFICACIONES:
--|             # @FECHA                
--|             # @DESCRIPCION
--|     # 
--| @PARAMETROS
--|     # 
--\____________________________________________________________________________________________________________________________________/

INSERT OVERWRITE TABLE ${esquema_cu}.cu_cap_relacion_cliente_alnova
SELECT 
     pdt08.num_cus as id_cliente_alnova 
    ,fin.id_cliente_finacle
    ,t065.id_cliente_unico
    ,t403.id_icu_digital
    ,fin.id_conversion
    ,t065.fec_ult_mod_cte_unico
    ,CURRENT_TIMESTAMP() AS fec_carga
    ,'ALNOVA' as cod_sistema
FROM(
    SELECT DISTINCT num_cus
    FROM rd_baz_bdclientes.rd_pedt008 
    ) AS pdt08
LEFT JOIN (
    SELECT
      CONCAT_WS(
        '-'
       ,TRIM(COALESCE(CAST(t065_acc_country AS VARCHAR), '0'))
       ,TRIM(COALESCE(CAST(t065_acc_channel AS VARCHAR), '0'))
       ,TRIM(COALESCE(CAST(t065_acc_brn     AS VARCHAR), '0'))
       ,TRIM(COALESCE(CAST(t065_acc_folio   AS VARCHAR), '0'))
      ) AS id_cliente_unico
    , t065_num_cus
    , t065_stp_last_mod AS fec_ult_mod_cte_unico
    FROM(
        SELECT
            t065_num_cus
          , t065_acc_country
          , t065_acc_channel
          , t065_acc_brn
          , t065_acc_folio
          , t065_dat_reg
          , t065_stp_last_mod
          , ROW_NUMBER() OVER (
              PARTITION BY t065_num_cus
              ORDER BY  t065_stp_last_mod DESC , t065_acc_folio ASC  ---cambio 1
            ) AS rn
        FROM rd_baz_bdclientes.rd_pedt065
        ) AS Ctes065
    WHERE rn = 1
    ) as t065 ON 
trim(pdt08.num_cus) = trim(t065.t065_num_cus)
LEFT JOIN (
    SELECT 
         t403_num_clte
        ,t403_bdmid as id_icu_digital
    FROM (
        SELECT 
             t403_num_clte
            ,t403_bdmid
            ,ROW_NUMBER() OVER (PARTITION BY t403_num_clte ORDER BY t403_stp_ultmod DESC) AS rn
        FROM rd_baz_bdclientes.rd_mcdt403
        ) x
    WHERE rn = 1
    ) as t403 ON 
TRIM(pdt08.num_cus) = TRIM(t403.t403_num_clte)
LEFT JOIN 
(
  SELECT     --segundo cambio
  id_cliente_alnova
  ,split_part(MIN(concat(id_cliente_finacle,'|',cast(id_conversion as string) )),"|",1) AS id_cliente_finacle
  ,cast(split_part(MIN(concat(id_cliente_finacle,'|',cast(id_conversion as string) )),"|",2) as int) AS id_conversion 
  FROM ${esquema_cu}.cu_cap_relacion_cliente_finacle
  WHERE id_cliente_alnova IS NOT NULL
  GROUP BY id_cliente_alnova
) fin on
trim(pdt08.num_cus) = trim(fin.id_cliente_alnova)
;

compute stats ${esquema_cu}.cu_cap_relacion_cliente_alnova;
