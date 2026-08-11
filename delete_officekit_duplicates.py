import csv
from connection.db_officekit import get_db
import logging
from datetime import datetime

logger = logging.getLogger("officekit_delete")
logger.setLevel(logging.INFO)
ch = logging.StreamHandler()
logger.addHandler(ch)

def run():
    company_code = "A100"
    sql_conn = get_db(company_code)
    
    if not sql_conn:
        logger.error("No SQL connection.")
        return
        
    cursor = sql_conn.cursor()
    
    with open('duplicate_faces.csv', 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["Company Code"] != company_code:
                continue
                
            code1 = row["Employee 1 Code"]
            date1 = row["Emp 1 Created Date"]
            code2 = row["Employee 2 Code"]
            date2 = row["Emp 2 Created Date"]
            
            if code1 == code2:
                continue
                
            d1 = datetime.strptime(date1, "%Y-%m-%d") if date1 != "Unknown" else datetime.now()
            d2 = datetime.strptime(date2, "%Y-%m-%d") if date2 != "Unknown" else datetime.now()
            
            if d1 <= d2:
                duplicate_code = code2
            else:
                duplicate_code = code1
                
            logger.info(f"Marking {duplicate_code} as IsDelete=1 in OfficeKit HR_EMP_MASTER")
            try:
                cursor.execute("""
                    UPDATE HR_EMP_MASTER 
                    SET IsDelete = 1 
                    WHERE Emp_Code = %s
                """, (duplicate_code,))
                sql_conn.commit()
            except Exception as e:
                logger.error(f"Failed to delete {duplicate_code} in OfficeKit: {e}")
                sql_conn.rollback()
                
if __name__ == "__main__":
    run()
