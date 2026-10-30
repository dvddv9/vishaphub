import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public class UserDao {
    private final Connection conn;

    public UserDao(Connection conn) {
        this.conn = conn;
    }

    public ResultSet find(String name) throws SQLException {
        PreparedStatement ps = conn.prepareStatement("SELECT id, email FROM users WHERE name = ?");
        ps.setString(1, name);
        return ps.executeQuery();
    }
}
