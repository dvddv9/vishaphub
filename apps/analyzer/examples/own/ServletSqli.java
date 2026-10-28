// Servlet SQL injection demo (source -> sink).
// Source: request.getParameter("id")
// Sink: Statement.executeQuery (string concat)
import javax.servlet.http.*;
import java.sql.*;

public class ServletSqli extends HttpServlet {
    private Connection conn;

    protected void doGet(HttpServletRequest req, HttpServletResponse resp) throws Exception {
        String id = req.getParameter("id");
        Statement stmt = conn.createStatement();
        ResultSet rs = stmt.executeQuery("SELECT * FROM users WHERE id = " + id);
        resp.getWriter().println(rs.next());
    }

    protected void doPost(HttpServletRequest req, HttpServletResponse resp) throws Exception {
        String cmd = req.getParameter("cmd");
        Runtime.getRuntime().exec(cmd);
    }
}
