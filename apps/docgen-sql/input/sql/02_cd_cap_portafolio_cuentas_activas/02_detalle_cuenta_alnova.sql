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
--| # Brenda Sarahi Rosas Morán <brenda.rosasm@algorithia.com>
--| @DESCRIPCION:                        
--|     # 
--| @TIEMPOS DE EJECUCION:      
--|     # 
--| @MODIFICACIONES:
--|             # @FECHA                
--|             # @DESCRIPCION
--|     # 
--| @PARAMETROS
--|     # ${esquema_cu} = ws_ec_cu_baz_bdclientes
--|     # ${fec_ini_sem} = 2026-04-27
--\____________________________________________________________________________________________________________________________________/

REFRESH ${esquema_cu}.cu_finacle_saldos_decrypt;
INVALIDATE METADATA ${esquema_cu}.cu_finacle_saldos_decrypt;
REFRESH  ${esquema_cu}.cu_cap_universo_cuentas  ;
INVALIDATE METADATA  ${esquema_cu}.cu_cap_universo_cuentas ;

INSERT OVERWRITE TABLE ${esquema_cu}.cu_cap_universo_cuentas  
PARTITION(COD_SISTEMA)
SELECT 
         CTA.NUM_CUS                                                            AS id_cliente
        ,CTA.BRN_OPEN                                                           AS ID_SUCURSAL_APERTURA                    
        ,concat(BRN_OPEN ,CTA.ACC)                                              AS ID_CUENTA
        ,IFNULL(FECHAS.t006_dat_preopn,CTA.DAT_REG)                             AS FEC_APERTURA
        ,IFNULL(FECHAS.t006_dat_can,CTA.dat_annulment)                          AS FEC_CANCELACION
        ,CTAINF.T041_CEN_ACCT                                                   AS ID_SUCURSAL_GESTORA
        ,CONCAT_WS("-",T041_COD_PRODUCT,T041_COD_SPROD)                         AS COD_PRODUCTO
        ,CTAINF.t041_dat_lastope                                                AS FEC_ULTIMA_TXN
        ,CTAINF.t041_num_operation                                              AS NUM_ULTIMA_TXN
        ,CTAINF.t041_cen_lastmod                                                AS ID_SUCURSAL_ULTIMA_TXN
        ,CTAINF.t041_lastmoduser                                                AS COD_USUARIO_ULTIMA_TXN
        ,IF(CTAINF.t041_flg_blockcod = 'S','BLOQUEADA','SIN BLOQUEO')           AS COD_BLOQUEO
        ,case
             when TRIM(CTA.KEY_PARTIC) ="1" then "1-PRETITULAR"
             when TRIM(CTA.KEY_PARTIC) ="2" then "2-PREFIADOR"
             when TRIM(CTA.KEY_PARTIC) ="3" then "3-PREREPRESENTANTE"
             when TRIM(CTA.KEY_PARTIC) ="4" then "4-PREDONANTE"
             when TRIM(CTA.KEY_PARTIC) ="5" then "5-PREAUTORIZADO"
             when TRIM(CTA.KEY_PARTIC) ="6" then "6-PREBENEFICIARIO"
             when TRIM(CTA.KEY_PARTIC) ="7" then "7-PRETUTOR"
             when TRIM(CTA.KEY_PARTIC) ="A" then "A-AUTORIZADO"
             when TRIM(CTA.KEY_PARTIC) ="B" then "B-BENEFICIARIO"
             when TRIM(CTA.KEY_PARTIC) ="C" then "C-CLIENTE/ASEGURADO"
             when TRIM(CTA.KEY_PARTIC) ="D" then "D-DONANTE"
             when TRIM(CTA.KEY_PARTIC) ="E" then "E-TUTOR"
             when TRIM(CTA.KEY_PARTIC) ="F" then "F-FIADOR"  
             when TRIM(CTA.KEY_PARTIC) ="G" then "G-GARANTE"
             when TRIM(CTA.KEY_PARTIC) ="H" then "H-HIPOTECANTE NO DEUDOR"
             when TRIM(CTA.KEY_PARTIC) ="K" then "K-FIADOR DESACTIVADO"
             when TRIM(CTA.KEY_PARTIC) ="M" then "M-MANCOMUNADO"
             when TRIM(CTA.KEY_PARTIC) ="O" then "O-OPERADOR"
             when TRIM(CTA.KEY_PARTIC) ="P" then "P-PROMOTOR"
             when TRIM(CTA.KEY_PARTIC) ="R" then "R-REPRESENTANTE"
             when TRIM(CTA.KEY_PARTIC) ="S" then "S-SUBROGANTE"
             when TRIM(CTA.KEY_PARTIC) ="T" then "T-TITULAR"
             when TRIM(CTA.KEY_PARTIC) ="U" then "U-USUFRUCTUARIO"
             when TRIM(CTA.KEY_PARTIC) ="V" then "V-AVALISTA"
             when TRIM(CTA.KEY_PARTIC) ="X" then "X-TITULAR ASEGURADO"
             when TRIM(CTA.KEY_PARTIC) ="Y" then "Y-ADMINISTRADOR"
             when TRIM(CTA.KEY_PARTIC) ="Z" then "Z-ACCIONISTA"
            else CONCAT(CTA.KEY_PARTIC,CTA.PARTSEQ)          
         END AS DESC_COD_TITULAR
        ,CASE WHEN CTAINF.T041_COD_RSNSUBJ ='301' THEN 'PF'
                        WHEN CTAINF.T041_COD_RSNSUBJ ='721' THEN 'PM'
                        ELSE ''
                END                                                             AS COD_TIPO_PERSONA
        ,CASE WHEN CTAINF.T041_FLG_STATUS = 'A' THEN 'ACTIVA'
                WHEN CTAINF.T041_FLG_STATUS = 'I' THEN 'INACTIVA'
                WHEN CTAINF.T041_FLG_STATUS = 'C' THEN 'CANCELADA'
                WHEN CTAINF.T041_FLG_STATUS = 'P' THEN 'PRECANCELADA'
                WHEN CTAINF.T041_FLG_STATUS = 'M' THEN 'MONEDERO' 
                ELSE CTAINF.t041_FLG_STATUS END AS COD_ESTATUS
        ,CTAINF.T041_FCC         AS COD_TIPO_MONEDA 
        ,CAST(CTAINF.T041_WDRWBAL AS DECIMAL(32,2))                              AS SLD_ACTUAL 
        ,DATEDIFF(now(),CTAINF.t041_dat_lastope)                                as num_dias_inactividad
        ,CAST('' AS STRING) AS plazodeposito
        /*,case 
        when concat(CAST(YEAR(CTA.DAT_REG) as string),
                CAST(WEEK(CTA.DAT_REG) as string)) 
                        between concat(CAST(YEAR(now()) as string)
                        ,CAST ((WEEK(DATE_ADD(now(),-7))) as string)) and concat(CAST(YEAR(now()) as string),CAST ((WEEK(now())) as string)) then 1
        end                                                                     as ind_cuenta_nueva
        */
        ,CASE
      WHEN IFNULL(FECHAS.t006_dat_preopn,CTA.DAT_REG)     >= DATE_ADD(NOW(), -7)
       AND IFNULL(FECHAS.t006_dat_preopn,CTA.DAT_REG)     < NOW()
      THEN 1
      ELSE 0
  END AS ind_cuenta_nueva
        ,DATEDIFF(now(),IFNULL(FECHAS.t006_dat_preopn,CTA.DAT_REG) )                                       as num_dias_antiguedad
        ,CURRENT_TIMESTAMP()                                                    AS FEC_CARGA
        ,'ALNOVA'                                                               AS COD_SISTEMA
FROM( 
        SELECT 
                 NUM_CUS       
                ,BRN_OPEN   
                ,COD_ENTITY
                ,KEY_PARTIC
                ,PARTSEQ
                ,CONCAT(COD_PRODSERV, NUM_ACCOUNT) AS ACC
                ,DAT_REG
                ,dat_annulment
        FROM rd_baz_bdclientes.rd_pedt008
        WHERE TO_DATE(DAT_REG) <= '${fec_ini_sem}' 
        ) CTA
INNER JOIN(
        SELECT
                 T041_ENT 
                ,T041_CEN_REG 
                ,T041_ACC
                ,T041_ENT_ACC   
                ,T041_CEN_ACCT  
                ,T041_COD_PRODUCT
                ,T041_COD_SPROD         
                ,T041_COD_RSNSUBJ
                ,T041_FCC
                ,T041_FLG_STATUS
                ,t041_dat_lastope 
                ,t041_num_operation
                ,t041_cen_lastmod
                ,t041_lastmoduser 
                ,t041_flg_blockcod 
                ,T041_WDRWBAL 
        FROM rd_baz_bdclientes.rd_bgdt041  
        ) CTAINF        ON        
CTA.COD_ENTITY = CTAINF.T041_ENT        AND 
CTA.BRN_OPEN = CTAINF.T041_CEN_REG      AND 
CTA.ACC = CTAINF.T041_ACC
LEFT JOIN 
rd_baz_bdclientes.rd_bgdt006 AS FECHAS ON
CTA.COD_ENTITY = FECHAS.T006_ENT        AND 
CTA.BRN_OPEN = FECHAS.T006_CEN_REG      AND 
CTA.ACC = FECHAS.T006_ACC
LEFT ANTI JOIN ${esquema_cu}.cu_finacle_saldos_decrypt AS FIN ON 
        CONCAT(CTA.BRN_OPEN ,CTA.ACC )= FIN.id_cuenta
;
COMPUTE STATS ${esquema_cu}.cu_cap_universo_cuentas;
 
